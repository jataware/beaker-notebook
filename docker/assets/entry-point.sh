#!/bin/sh
CMD=${CMD:-python3}
ARGS=${ARGS:-$@}
PRE_EXEC_DIR=/usr/local/bin/pre-exec
if [ -d "$PRE_EXEC_DIR" ]; then
    for file in `ls $PRE_EXEC_DIR/* 2>/dev/null`; do
        if [ -x "$file" ]; then
            echo "Executing pre-execution script $file:"
            command $file
            echo "Finished script $file"
        fi
    done
fi

if [ -z "$RUN_USER" ]; then
    exec $CMD $ARGS
else
    exec gosu "${RUN_USER}" $CMD $ARGS
fi
