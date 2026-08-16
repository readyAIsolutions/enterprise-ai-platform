#!/usr/bin/env bash
# eni_record_fail.sh <model> — record a model failure for 120s demotion.
[ -n "$1" ] && echo "$1=$(date +%s)" >> /tmp/eni_model_health
