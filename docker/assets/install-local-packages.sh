#!/bin/bash
PACKAGE_DIR=/opt/development/packages
PACKAGE_LIST_FILE=/opt/package_list

if [[ ! -e "$PACKAGE_LIST_FILE" ]]; then
    echo "all" > $PACKAGE_LIST_FILE
fi

for dir in $PACKAGE_DIR/*; do
    dirname=$(basename $dir)
    if grep all $PACKAGE_LIST_FILE > /dev/null 2>&1 || grep $dirname $PACKAGE_LIST_FILE > /dev/null 2>&1; then
    (
        echo 'Installing package "'$dirname'" from '$dir'...'
        cd $dir
        uv pip install --system -e .
    )
    else
        echo Skipping $dirname...
    fi
done
