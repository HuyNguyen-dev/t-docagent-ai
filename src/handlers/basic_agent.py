from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from agents.basic import basic_graph
from schemas.llm import LLMResponse
from utils.enums import ModelType
from utils.logger.custom_logging import LoggerMixin


class BasicAgent(LoggerMixin):
    async def ainvoke_graph_flow(
        self,
        model_name: ModelType,
        question: str,
    ) -> StreamingResponse:
        messages = [
            HumanMessage(content=question),
        ]
        llm_response = await basic_graph.ainvoke(
            input={"messages": messages},
            config={"configurable": {"model_name": model_name}},
        )
        return llm_response["messages"][-1].content

    async def astream_graph_flow(
        self,
        model_name: ModelType,
        question: str,
    ) -> str | None:
        messages = [
            HumanMessage(content=question),
        ]

        async def response_generator(model_name: str) -> AsyncGenerator:
            async for event in basic_graph.astream_events(
                input={"messages": messages},
                config={"configurable": {"model_name": model_name}},
                stream_mode="messages",
            ):
                type_event = event["event"]
                if type_event == "on_tool_start":
                    self.logger.debug(
                        "event=start-call-tool tool-name=%s tool-input=%s ",
                        event["name"],
                        event["data"]["input"],
                    )
                if type_event == "on_chat_model_stream" and event["data"]["chunk"].content:
                    self.logger.debug(
                        "event=stream-response chunk=%s",
                        event["data"]["chunk"].content,
                    )
                    yield (
                        LLMResponse(
                            model=model_name,
                            data=event["data"]["chunk"].content,
                            done=False,
                        ).model_dump_json()
                        + "\n"
                    )
            yield (
                LLMResponse(
                    model=model_name,
                    data="",
                    done=True,
                ).model_dump_json()
                + "\n"
            )

        return StreamingResponse(
            response_generator(model_name),
            media_type="application/x-ndjson",
        )
