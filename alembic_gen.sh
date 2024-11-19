#!/usr/bin/env sh
# Usage: ./alembic_gen.sh "Add new column to table"
cd tagstudio
alembic revision --autogenerate -m "$1"
