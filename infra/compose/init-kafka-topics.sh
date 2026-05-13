#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:9092}"
TOPICS=(
  "diagnostic-findings.v1"
  "vehicle-telemetry.v1"
  "policy-deployments.v1"
  "policy-outcomes.v1"
)

for t in "${TOPICS[@]}"; do
  /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists \
    --topic "$t" \
    --partitions 3 \
    --replication-factor 1
done

echo "kafka topics initialized: ${TOPICS[*]}"
