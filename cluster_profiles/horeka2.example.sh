#!/usr/bin/env bash
# Copy outside Git, replace values with settings verified on the target cluster.
# Deliberately not executable as a ready-to-use Horeka-2 configuration.
echo "Configure a private Horeka-2 profile first; see Readmes/pipeline_phases.md" >&2
return 1
# export CONFIG="/verified/path/config.horeka2.json"
# export BIOOTON_ENV_PREFIX="/verified/path/core"
# export BIOOTON_BACPIPE_ENV_PREFIX="/verified/path/bacpipe"
# export PYTHON="/verified/path/core/bin/python"
# export BIOOTON_BACPIPE_PYTHON="/verified/path/bacpipe/bin/python"
# export BIOOTON_PARTITION="${BIOOTON_PARTITION:-verified-partition}"
# export BIOOTON_BIOACOUSTICS_PARTITION="${BIOOTON_BIOACOUSTICS_PARTITION:-$BIOOTON_PARTITION}"
# export BIOOTON_ACCOUNT="${BIOOTON_ACCOUNT:-verified-account}"
# export BIOOTON_CONSTRAINT="${BIOOTON_CONSTRAINT-}"  # Empty omits --constraint.
# Optional GPU resources, only after model/runtime validation:
# export BIOOTON_BIOACOUSTICS_GRES="${BIOOTON_BIOACOUSTICS_GRES:-gpu:1}"
