source env.sh

start() {
  # Check the operating system type
  if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    # Windows-like environment
    python "$SRC_DIR/app.py"
  else
    # Linux-like environment
    python3 "$SRC_DIR/app.py"
  fi
}

start
