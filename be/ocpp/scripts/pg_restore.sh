#!/bin/sh

pg_restore --clean -h 127.0.0.1 -v -U levity -d levity -j 2 $1