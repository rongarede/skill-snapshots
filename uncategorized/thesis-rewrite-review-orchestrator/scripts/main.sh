#!/bin/bash
# thesis-rewrite-review-orchestrator: isolated rewrite/review loop controller

set -euo pipefail

OUT_DIR="tmp/ch2_rounds"
ROUND=1
MAX_ROUNDS=6
TARGET_FILE=""
EXEC_LOG=""
PEER_REPORT=""
ACADEMIC_REPORT=""
SUPPORT_REPORT=""

usage() {
  cat <<'USAGE'
Usage:
  main.sh init --target <file> [--out <dir>] [--round <n>] [--max-rounds <n>] [--execution-log <file>]
  main.sh prep-round [--out <dir>] [--round <n>] [--target <file>]
  main.sh gate [--out <dir>] [--round <n>] [--max-rounds <n>] [--peer <file>] [--academic <file>] [--support <file>]
  main.sh status [--out <dir>]
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_file() {
  local f="$1"
  [[ -f "$f" ]] || die "file not found: $f"
}

round_dir() {
  local n="$1"
  echo "$OUT_DIR/round-$n"
}

create_round_layout() {
  local n="$1"
  local rd
  rd="$(round_dir "$n")"

  mkdir -p "$rd/rewrite" "$rd/review" "$rd/support" "$rd/gate"

  if [[ ! -f "$rd/rewrite/context.md" ]]; then
    cat > "$rd/rewrite/context.md" <<EOF_CTX
# rewrite context (round-$n)

## inputs
- target_file: ${TARGET_FILE:-<set-target-file>}
- must_fix: []
- optional_fix: []

## guardrails
- do not include raw review chain-of-thought
- do not change cite/ref/label keys
EOF_CTX
  fi

  if [[ ! -f "$rd/review/context_peer.md" ]]; then
    cat > "$rd/review/context_peer.md" <<'EOF_CTX'
# peer review context

## inputs
- candidate: rewrite/candidate.tex
- checklist: Critical/Major/Minor

## output contract
- decision: PASS/FAIL
- must_fix: []
- optional_fix: []
EOF_CTX
  fi

  if [[ ! -f "$rd/review/context_academic.md" ]]; then
    cat > "$rd/review/context_academic.md" <<'EOF_CTX'
# academic writing review context

## inputs
- candidate: rewrite/candidate.tex
- checklist: academic tone / argument chain / coherence

## output contract
- decision: PASS/FAIL
- must_fix: []
- optional_fix: []
EOF_CTX
  fi

  if [[ ! -f "$rd/support/context.md" ]]; then
    cat > "$rd/support/context.md" <<EOF_CTX
# supportability context

## inputs
- chapter2: ${TARGET_FILE:-<set-target-file>}
- chapter3: chapters/chapter3.tex
- chapter4: chapters/chapter4.tex

## output contract
- mapping matrix (Covered/Weak/Missing)
- Missing count
- decision: PASS/FAIL
EOF_CTX
  fi
}

extract_decision() {
  local report="$1"
  local d
  d=$(grep -Eio '^[[:space:]]*decision[[:space:]]*:[[:space:]]*(PASS|FAIL)' "$report" | tail -1 | awk -F: '{gsub(/[[:space:]]/,"",$2); print toupper($2)}' || true)
  if [[ -z "$d" ]]; then
    echo "UNKNOWN"
  else
    echo "$d"
  fi
}

extract_missing_count() {
  local report="$1"
  local n

  n=$(grep -Eio 'Missing count[[:space:]]*:[[:space:]]*\**[0-9]+' "$report" | tail -1 | grep -Eo '[0-9]+' || true)
  if [[ -n "$n" ]]; then
    echo "$n"
    return
  fi

  n=$(grep -Eio 'Missing[[:space:]]*=[[:space:]]*[0-9]+' "$report" | tail -1 | grep -Eo '[0-9]+' || true)
  if [[ -n "$n" ]]; then
    echo "$n"
    return
  fi

  echo "-1"
}

extract_must_fix_block() {
  local report="$1"
  awk '
    BEGIN {capture=0;printed=0}
    tolower($0) ~ /^must_fix[[:space:]]*:?/ {capture=1; next}
    capture {
      if (tolower($0) ~ /^(optional_fix|resolved|blockers|minor|major|critical)[[:space:]]*:?/) exit
      if ($0 ~ /^[[:space:]]*$/) {
        if (printed==1) exit
        next
      }
      print
      printed=1
    }
  ' "$report"
}

write_must_fix_summary() {
  local rd="$1"
  local out="$rd/gate/must_fix.md"
  local peer_block academic_block support_block

  peer_block="$(extract_must_fix_block "$PEER_REPORT" || true)"
  academic_block="$(extract_must_fix_block "$ACADEMIC_REPORT" || true)"
  support_block="$(extract_must_fix_block "$SUPPORT_REPORT" || true)"

  {
    echo "# round-$ROUND must_fix summary"
    echo
    echo "## peer-review"
    if [[ -n "${peer_block// }" ]]; then
      echo "$peer_block"
    else
      echo "- []"
    fi
    echo
    echo "## academic-writing"
    if [[ -n "${academic_block// }" ]]; then
      echo "$academic_block"
    else
      echo "- []"
    fi
    echo
    echo "## supportability"
    if [[ -n "${support_block// }" ]]; then
      echo "$support_block"
    else
      echo "- []"
    fi
  } > "$out"
}

cmd_init() {
  [[ -n "$TARGET_FILE" ]] || die "--target is required"
  require_file "$TARGET_FILE"

  mkdir -p "$OUT_DIR"
  create_round_layout "$ROUND"

  if [[ -z "$EXEC_LOG" ]]; then
    EXEC_LOG="docs/todo/$(date +%F)-chapter2-round-execution.md"
  fi

  mkdir -p "$(dirname "$EXEC_LOG")"
  if [[ ! -f "$EXEC_LOG" ]]; then
    cat > "$EXEC_LOG" <<EOF_LOG
# $(date +%F) chapter rewrite-review execution log

- target: $TARGET_FILE
- out_dir: $OUT_DIR
- max_rounds: $MAX_ROUNDS

## rounds

EOF_LOG
  fi

  echo "initialized: $(round_dir "$ROUND")"
  echo "execution_log: $EXEC_LOG"
}

cmd_prep_round() {
  [[ "$ROUND" -ge 1 ]] || die "round must be >= 1"
  create_round_layout "$ROUND"
  echo "prepared: $(round_dir "$ROUND")"
}

cmd_gate() {
  local rd
  rd="$(round_dir "$ROUND")"

  PEER_REPORT="${PEER_REPORT:-$rd/review/peer_report.md}"
  ACADEMIC_REPORT="${ACADEMIC_REPORT:-$rd/review/academic_report.md}"
  SUPPORT_REPORT="${SUPPORT_REPORT:-$rd/support/supportability_report.md}"

  require_file "$PEER_REPORT"
  require_file "$ACADEMIC_REPORT"
  require_file "$SUPPORT_REPORT"

  local peer_dec academic_dec support_dec missing_count final_dec

  peer_dec="$(extract_decision "$PEER_REPORT")"
  academic_dec="$(extract_decision "$ACADEMIC_REPORT")"
  support_dec="$(extract_decision "$SUPPORT_REPORT")"
  missing_count="$(extract_missing_count "$SUPPORT_REPORT")"

  final_dec="FAIL"
  if [[ "$peer_dec" == "PASS" && "$academic_dec" == "PASS" && "$support_dec" == "PASS" && "$missing_count" == "0" ]]; then
    final_dec="PASS"
  fi

  write_must_fix_summary "$rd"

  {
    echo "decision: $final_dec"
    echo
    echo "peer_review: $peer_dec"
    echo "academic_writing: $academic_dec"
    echo "supportability: $support_dec"
    echo "missing_count: $missing_count"
    echo "round: $ROUND"
    echo "max_rounds: $MAX_ROUNDS"
    echo
    if [[ "$final_dec" == "PASS" ]]; then
      echo "next_action: stop-loop"
    elif [[ "$ROUND" -lt "$MAX_ROUNDS" ]]; then
      echo "next_action: continue-to-round-$((ROUND + 1))"
    else
      echo "next_action: stop-loop(max-rounds-reached)"
    fi
  } > "$rd/gate/decision.md"

  if [[ "$final_dec" != "PASS" && "$ROUND" -lt "$MAX_ROUNDS" ]]; then
    create_round_layout "$((ROUND + 1))"
  fi

  cat "$rd/gate/decision.md"
}

cmd_status() {
  [[ -d "$OUT_DIR" ]] || die "out dir not found: $OUT_DIR"

  local local_name decision_file dec
  for rd in "$OUT_DIR"/round-*; do
    [[ -d "$rd" ]] || continue
    local_name="$(basename "$rd")"
    decision_file="$rd/gate/decision.md"
    if [[ -f "$decision_file" ]]; then
      dec=$(grep -Eio '^decision:[[:space:]]*(PASS|FAIL)' "$decision_file" | awk -F: '{gsub(/[[:space:]]/,"",$2); print toupper($2)}' || true)
      [[ -n "$dec" ]] || dec="UNKNOWN"
      echo "$local_name: $dec"
    else
      echo "$local_name: PENDING"
    fi
  done
}

parse_args() {
  local cmd="$1"
  shift

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --out)
        OUT_DIR="$2"; shift 2 ;;
      --round)
        ROUND="$2"; shift 2 ;;
      --max-rounds)
        MAX_ROUNDS="$2"; shift 2 ;;
      --target)
        TARGET_FILE="$2"; shift 2 ;;
      --execution-log)
        EXEC_LOG="$2"; shift 2 ;;
      --peer)
        PEER_REPORT="$2"; shift 2 ;;
      --academic)
        ACADEMIC_REPORT="$2"; shift 2 ;;
      --support)
        SUPPORT_REPORT="$2"; shift 2 ;;
      -h|--help)
        usage; exit 0 ;;
      *)
        die "unknown argument: $1" ;;
    esac
  done

  case "$cmd" in
    init) cmd_init ;;
    prep-round) cmd_prep_round ;;
    gate) cmd_gate ;;
    status) cmd_status ;;
    *) usage; die "unknown command: $cmd" ;;
  esac
}

main() {
  [[ $# -ge 1 ]] || { usage; exit 1; }
  if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
    exit 0
  fi
  parse_args "$@"
}

main "$@"
