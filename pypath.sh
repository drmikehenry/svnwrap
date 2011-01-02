# This script must be "source'd"

DEVELOP="`pwd`/$1"
NAME=`basename $0`

if [ x"$1" == x"" ]; then
    echo "Must supply relative path to develop directory"

elif [ "$NAME" != "sh" ] && [ "$NAME" != "bash" ]; then
    echo "Must 'source' this script via 'source $NAME'"

elif [ ! -d "$DEVELOP" ]; then
    echo "Missing develop directory $DEVELOP"

else
    export PATH="$DEVELOP:$PATH"
    export PYTHONPATH="$DEVELOP:$PYTHONPATH"

    echo "Updated PATH and PYTHONPATH to include the directory:"
    echo "    $DEVELOP"
fi
