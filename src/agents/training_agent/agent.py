from asyncio import TaskGroup
from datetime import datetime

from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.training_agent.nodes import AnalyzeMetricsNode, ExtractionNode, MappingNode
from agents.training_agent.state import TrainingState
from handlers.document import DocumentHandler
from initializer import redis_pubsub_manager, training_status_manager
from models.document_content import DocumentContent
from models.document_format import DocumentFormat
from models.document_type import DocumentType
from models.document_work_item import DocumentWorkItem
from schemas.document_content import DocumentContentTable, ExtractedContent
from schemas.training import FieldExtractionData, GenExtractionData, PerformanceMetrics, TableExtractionData
from settings.prompts.training import CHAIN_OF_THOUGHT_MESSAGE_SYSTEM, FIELD_EXTRACTION_PROMPT, TABLE_EXTRACTION_PROMPT
from utils.constants import TIMEZONE
from utils.enums import DocumentContentState, DocumentFormatState, DocWorkItemStage, DocWorkItemState, FileType, RedisChannelName
from utils.logger.custom_logging import LoggerMixin


class ExtractionAgent(LoggerMixin):
    """
    Validated extraction agent that implements a LangGraph workflow using DocumentType models.
    """

    def __init__(self, extraction_node: ExtractionNode) -> None:
        super().__init__()
        self.extraction_node = extraction_node
        self.mapping_node = MappingNode()
        self.analyze_metrics_node = AnalyzeMetricsNode()
        self.workflow_graph = self._build_graph()
        self.document_handler = DocumentHandler()
        self.logger.info(
            'event=extraction-agent-initialized message="Extraction agent initialized successfully"',
        )

    @classmethod
    async def create(cls) -> "ExtractionAgent":
        extraction_node = await ExtractionNode.create()
        return cls(extraction_node)

    def _build_graph(self) -> CompiledStateGraph:
        """
        Build the LangGraph workflow.
        """
        self.logger.debug(
            'event=build-extraction-graph message="Building extraction workflow graph"',
        )
        workflow_graph = StateGraph(TrainingState)

        # Define nodes
        workflow_graph.add_node("extract_using_chain_of_thought_node", self._extract_using_chain_of_thought_node)
        workflow_graph.add_node("mapping", self._mapping_node)
        workflow_graph.add_node("analyze_metrics", self._analyze_metrics_node)

        # Define edges
        workflow_graph.add_edge(START, "extract_using_chain_of_thought_node")
        # Connect chain_of_thought to mapping
        workflow_graph.add_edge("extract_using_chain_of_thought_node", "mapping")
        # Continue the flow
        workflow_graph.add_edge("mapping", "analyze_metrics")

        self.logger.debug(
            'event=extraction-graph-built message="Extraction workflow graph built successfully"',
        )
        return workflow_graph.compile()

    async def _extract_using_chain_of_thought_node(self, state: TrainingState) -> TrainingState:
        """
        Node that extracts document fields and tables using a chain of thought approach.
        """
        self.logger.info(
            'event=start-chain-of-thought-extraction message="Starting extraction using chain of thought"',
        )
        if state["document_format"].fields and not state["document_format"].tables:
            state["system_message"] = FIELD_EXTRACTION_PROMPT
            state["output_parser"] = FieldExtractionData
        elif state["document_format"].tables and not state["document_format"].fields:
            state["system_message"] = TABLE_EXTRACTION_PROMPT
            state["output_parser"] = TableExtractionData
        else:
            state["system_message"] = CHAIN_OF_THOUGHT_MESSAGE_SYSTEM
            state["output_parser"] = GenExtractionData
        if not state.get("base64_images"):
            self.logger.warning(
                'event=missing-images message="No images provided for extraction"',
            )
            state["error"] = "No images provided for extraction"
            return state
        self.logger.info(
            'event=invoke-chain-of-thought message="Invoking chain of thought extraction"',
        )
        try:
            result = await self.extraction_node.extract_using_chain_of_thought(state)
            if result is None:
                self.logger.warning(
                    'event=chain-of-thought-extraction-failed message="Failed to extract data using chain of thought"',
                )
                state["error"] = "Failed to extract data using chain of thought"
                return state

            state["extracted_fields"] = getattr(result, "fields", {})
            state["extracted_tables"] = getattr(result, "tables", [])
            self.logger.info(
                'event=chain-of-thought-extracted message="Data extracted successfully using chain of thought" data=%s',
                result.model_dump_json(),
            )
        except Exception:
            self.logger.exception(
                'event=chain-of-thought-extraction-error message="Error during chain of thought extraction"',
            )
            state["error"] = "Error during chain of thought extraction"
            return state
        return state

    async def _mapping_node(self, state: TrainingState) -> TrainingState:
        """
        Node that maps extracted data to target format based on document format.
        """
        if not state.get("document_format"):
            self.logger.info(
                'event=skip-mapping message="No document format provided, skipping mapping"',
            )
            return state

        self.logger.info(
            'event=start-mapping message="Starting data mapping to target format"',
        )
        mapped_state = self.mapping_node.map_extraction(state)

        if mapped_state.get("mapped_fields"):
            self.logger.info(
                'event=fields-mapped message="Fields mapped successfully" data=%s',
                mapped_state["mapped_fields"],
            )
        if mapped_state.get("mapped_tables"):
            self.logger.info(
                'event=tables-mapped message="Tables mapped successfully" data=%s',
                mapped_state["mapped_tables"],
            )

        return mapped_state

    async def _analyze_metrics_node(self, state: TrainingState) -> TrainingState:
        """
        Node that analyzes metrics after all processing is complete.
        """
        self.logger.info(
            'event=start-metrics-analysis message="Starting metrics analysis"',
        )

        # Analyze all metrics
        state = await self.analyze_metrics_node.analyze_metrics(state)

        self.logger.info(
            'event=metrics-analysis-completed message="Metrics analysis completed"',
        )

        return state

    async def update_status_document_work_item(self, dwi_id: str, stage: str, state: str) -> bool:
        try:
            dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.id == dwi_id)
            if dwi_db:
                dwi_db.stage = stage
                dwi_db.state = state
                dwi_db.last_run = datetime.now(TIMEZONE)
                await dwi_db.save()
            self.logger.info(
                "event=updated-stage/state-document-work-item-successfully "
                'message="Update state and stage for document work item successfully"',
            )
        except Exception:
            self.logger.exception(
                'event=failed-to-update-stage/state-document-work-item message="Failed to stage/state state DWI"',
            )
            return False
        return True

    async def _save_extracted_content_into_db(
        self,
        dwi_id: str,
        extracted_content: ExtractedContent,
        state: TrainingState,
    ) -> bool:
        try:
            dc_db = await DocumentContent.find_one(
                DocumentContent.dwi_id == dwi_id,
            )

            if dc_db:
                dc_db.extracted_content = extracted_content
                dc_db.state = DocumentContentState.EXTRACTED
                dc_db.metadata = state.get("result_summary", {})
                await dc_db.save()
            else:
                new_doc_content = DocumentContent(
                    dwi_id=dwi_id,
                    state=DocumentContentState.EXTRACTED,
                    extracted_content=extracted_content,
                    metadata=state.get("result_summary", {}),
                )
                await new_doc_content.insert()
            self.logger.info(
                'event=saved-extracted-content-successfully message="Save extracted content into database successfully"',
            )
        except Exception:
            self.logger.exception(
                'event=failed-to-save-extracted-content message="Failed to save extracted content into database"',
            )
            return False
        return True

    async def _run_flow(
        self,
        dt_db: DocumentType,
        df_db: DocumentFormat,
        doc_uri: str,
    ) -> dict | None:
        try:
            base64_image = await self.document_handler.get_data_document(object_path=doc_uri)
            if not base64_image:
                self.logger.error(
                    'event=fetch-document-file-by-doc-uri-failed doc_uri=%s message="Failed to fetch document file by doc_uri"',
                    doc_uri,
                )
                return {"is_success": False}

            file_entension = doc_uri.split(".")[-1].lower()
            initial_state = TrainingState(
                base64_images=[base64_image],
                document_type=dt_db,
                document_format=df_db,
                metrics=PerformanceMetrics(),
                start_time=datetime.now(TIMEZONE),
                is_pdf=FileType.from_extension(file_entension) == FileType.PDF,
            )
            self.logger.info('event=invoke-workflow message="Invoking extraction workflow"')
            final_state: TrainingState = await self.workflow_graph.ainvoke(initial_state)
            has_error = bool(final_state.get("error"))
            if has_error:
                self.logger.error(
                    'event=extraction-failed message="Extraction failed"',
                )

            mapped_tables = final_state.get("mapped_tables", {})
            mapped_fields = final_state.get("mapped_fields", {})
            extracted_tables = [
                DocumentContentTable(id=tbl.get("table_id"), columns=tbl.get("columns", [])) for tbl in mapped_tables.values()
            ]
            extracted_content = ExtractedContent(
                fields=mapped_fields,
                tables=extracted_tables,
            )
        except Exception:
            self.logger.exception(
                'event=process-run-extraction-failed message="Extraction failed"',
            )
            return {"is_success": False}
        return {
            "final_state": final_state,
            "extracted_content": extracted_content,
            "has_error": has_error,
            "is_success": True,
        }

    async def put_event_message(self, dt_id: str, message: dict) -> None:
        """Helper function to publish message to the specific document type channel"""
        channel = f"{RedisChannelName.DOCUMENT_TYPE}:{dt_id}"
        await redis_pubsub_manager.publish(channel, message)

    async def run(
        self,
        dt_name: str,
        df_name: str,
        doc_uri: str,
        is_workflow: bool = False,
    ) -> None:
        try:
            is_success = True
            self.logger.info(
                'event=start-extraction message="Starting document extraction process"',
            )
            dwi_db = await DocumentWorkItem.find_one(DocumentWorkItem.doc_uri == doc_uri)
            dt_db = await DocumentType.find_one(DocumentType.name == dt_name)
            df_db = await DocumentFormat.find_one(DocumentFormat.name == df_name)

            message = {
                "dwi": None,
                "state": DocWorkItemState.FAILED.value,
            }
            if not dwi_db:
                self.logger.error(
                    'event=document-work-item-not-found message="No DocumentWorkItem found for given format"',
                )
                return

            message["dwi"] = dwi_db.id
            if not dt_db or not df_db:
                self.logger.error(
                    'event=missing-document-type-or-formatmessage="Document type or format was not found"',
                )
                is_success = False
                return

            if not (
                (dwi_db.stage is DocWorkItemStage.EXTRACTION and dwi_db.state is DocWorkItemState.IN_PROCESS)
                or (dwi_db.stage is DocWorkItemStage.EXTRACTION and df_db.state is DocumentFormatState.RETRAIN)
            ):
                self.logger.warning(
                    "event=document-work-item-was-extracted "
                    'message="Document worker item is not in training or completed and not Retrain Document Format"',
                )
                return

            is_set = await training_status_manager.set_training_status(
                dwi_id=dwi_db.id,
                dt_id=dt_db.id,
            )
            if not is_set:
                return

            contents = await self._run_flow(dt_db=dt_db, df_db=df_db, doc_uri=doc_uri)
            is_success = contents["is_success"]
            if not is_success:
                return

            is_success = not contents["has_error"]
            final_state: TrainingState = contents["final_state"]
            extracted_content: ExtractedContent = contents["extracted_content"]

            is_saved_document_content = await self._save_extracted_content_into_db(
                dwi_id=dwi_db.id,
                extracted_content=extracted_content,
                state=final_state,
            )
            if not is_saved_document_content:
                self.logger.error(
                    'event=save-extracted-content-failed message="Failed to save extracted content into database"',
                )
                is_success = False
                return

            is_updated_state_dwi = await self.update_status_document_work_item(
                dwi_id=dwi_db.id,
                stage=DocWorkItemStage.EXTRACTION,
                state=DocWorkItemState.COMPLETED,
            )

            if not is_updated_state_dwi:
                self.logger.error(
                    'event=update-state-dwi-failed message="Failed to update state DWI"',
                )
                is_success = False
                return

            if is_success:
                self.logger.info(
                    'event=document-work-item-was-extractedmessage="Worker item was extracted successfully"',
                )
                message["state"] = DocWorkItemState.COMPLETED.value

                is_removed = await training_status_manager.remove_training_status(dwi_db.id)
                if not is_removed:
                    return
        except Exception:
            self.logger.exception(
                'event=process-run-extraction-failed message="Extraction failed"',
            )
            return
        finally:
            if not is_success:
                await self.update_status_document_work_item(
                    dwi_id=dwi_db.id,
                    stage=DocWorkItemStage.EXTRACTION,
                    state=DocWorkItemState.FAILED,
                )

            if not is_workflow:
                await self.put_event_message(dt_db.id, message)

    async def run_extraction_transiently(
        self,
        dt_name: str,
        df_name: str,
        doc_uri: str,
    ) -> dict | None:
        try:
            is_success = True
            self.logger.info(
                'event=start-extraction message="Starting document extraction process"',
            )
            dt_db = await DocumentType.find_one(DocumentType.name == dt_name)
            df_db = await DocumentFormat.find_one(DocumentFormat.name == df_name)
            if not dt_db or not df_db:
                self.logger.error(
                    'event=missing-document-type-or-formatmessage="Document type or format was not found"',
                )
                is_success = False
                return None
            contents = await self._run_flow(dt_db=dt_db, df_db=df_db, doc_uri=doc_uri)
            is_success = contents["is_success"]
            if not is_success:
                return None

            is_success = not contents["has_error"]
            final_state: TrainingState = contents["final_state"]
            extracted_content: ExtractedContent = contents["extracted_content"]

            return {
                "has_error": not is_success,
                "extracted_content": extracted_content,
                "metadata": final_state.get("result_summary", {}),
            }
        except Exception:
            self.logger.exception(
                'event=process-run-extraction-failed message="Extraction failed"',
            )
            return None

    async def run_extraction_batch(
        self,
        dt_name: str,
        df_name: str,
        doc_uris: list[str],
    ) -> list[dict] | None:
        try:
            self.logger.info(
                'event=start-batch-extraction message="Starting batch extraction" size=%d',
                len(doc_uris),
            )
            if not doc_uris:
                return []

            dt_db = await DocumentType.find_one(DocumentType.name == dt_name)
            df_db = await DocumentFormat.find_one(DocumentFormat.name == df_name)
            if not dt_db or not df_db:
                self.logger.error(
                    'event=batch-missing-document-type-or-format message="Document type or format not found"',
                )
                return None

            base64_images_list: list[str | None] = [None] * len(doc_uris)
            async with TaskGroup() as tg:
                for idx, uri in enumerate(doc_uris):
                    async def _fetch(i: int, u: str) -> None:
                        base64_images_list[i] = await self.document_handler.get_data_document(object_path=u)
                    tg.create_task(_fetch(idx, uri))

            initial_states: list[TrainingState] = []
            for uri, base64_image in zip(doc_uris, base64_images_list, strict=False):
                if not base64_image:
                    self.logger.error(
                        'event=fetch-document-file-by-doc-uri-failed doc_uri=%s"',
                        uri,
                    )
                    initial_states.append(
                        TrainingState(
                            base64_images=[],
                            document_type=dt_db,
                            document_format=df_db,
                            metrics=PerformanceMetrics(),
                            start_time=datetime.now(TIMEZONE),
                            is_pdf=False,
                            error="Failed to fetch document",
                        ),
                    )
                    continue

                file_entension = uri.split(".")[-1].lower()
                initial_states.append(
                    TrainingState(
                        base64_images=[base64_image],
                        document_type=dt_db,
                        document_format=df_db,
                        metrics=PerformanceMetrics(),
                        start_time=datetime.now(TIMEZONE),
                        is_pdf=FileType.from_extension(file_entension) == FileType.PDF,
                    ),
                )

            final_states: list[TrainingState] = []
            try:
                final_states = await self.workflow_graph.abatch(initial_states)
            except Exception:
                final_states = [None] * len(initial_states)
                async with TaskGroup() as tg2:
                    for i, st in enumerate(initial_states):
                        async def _invoke(idx: int, _state: TrainingState) -> None:
                            final_states[idx] = await self.workflow_graph.ainvoke(_state)
                        tg2.create_task(_invoke(i, st))

            results: list[dict] = []
            for st in final_states:
                has_error = bool(st.get("error")) if st else True
                if not st or has_error:
                    results.append(
                        {
                            "has_error": True,
                            "extracted_content": None,
                            "metadata": {},
                        },
                    )
                    continue
                mapped_tables = st.get("mapped_tables", {})
                mapped_fields = st.get("mapped_fields", {})
                extracted_tables = [
                    DocumentContentTable(id=tbl.get("table_id"), columns=tbl.get("columns", [])) for tbl in mapped_tables.values()
                ]
                extracted_content = ExtractedContent(
                    fields=mapped_fields,
                    tables=extracted_tables,
                )
                results.append(
                    {
                        "has_error": False,
                        "extracted_content": extracted_content,
                        "metadata": st.get("result_summary", {}),
                    },
                )

        except Exception:
            self.logger.exception(
                'event=batch-extraction-failed message="Batch extraction failed"',
            )
            return None
        return results
