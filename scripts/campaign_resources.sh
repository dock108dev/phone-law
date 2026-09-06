# Shared by disposable gate entry points, after their paths are selected.
# Claim succeeds before any cleanup trap is installed.
export COLACCI_CAMPAIGN_TOKEN="$$-${RANDOM}-${RANDOM}"
campaign_resource() {
  PYTHONPATH="$repository_root" python3 "$repository_root/scripts/campaign_resources.py" \
    "$1" "$project_name" "$runtime_root" "$evidence_root"
}
campaign_claim() {
  campaign_resource claim
}
campaign_cleanup_stack() {
  campaign_resource check || return
  docker compose -p "$project_name" --profile e2e down -v --remove-orphans || return
  campaign_resource verify-clean
}
campaign_cleanup() {
  campaign_cleanup_stack || return
  campaign_resource secure || return
  campaign_resource remove
}
