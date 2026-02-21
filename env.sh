#!/usr/bin/env bash

APP_HOME="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export APP_HOME="$APP_HOME"
export SRC_DIR="$APP_HOME/src"
export PYTHONPATH="$PYTHONPATH:$APP_HOME:$SRC_DIR"
