#!/usr/bin/env bash
set -euo pipefail

: "${E2E_EMAIL:?E2E_EMAIL is required}"
: "${E2E_PASSWORD:?E2E_PASSWORD is required}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-knowledge_base}"

payload="$(jq -n --arg email "$E2E_EMAIL" --arg password "$E2E_PASSWORD" '{email: $email, password: $password}')"
registration="$(curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -X POST \
  --data "$payload" \
  http://127.0.0.1:8000/auth/register)"
printf '%s\n' "$registration" | jq -e '.email_verified == true' >/dev/null

user_id="$(docker compose exec -T db psql \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -qAtc \
  "SELECT id FROM users WHERE email = '$E2E_EMAIL'")"
if [[ ! "$user_id" =~ ^[0-9]+$ ]]; then
  echo "Could not resolve registered E2E user id" >&2
  exit 1
fi

document_content="A seeded full-stack E2E document."
content_sha256="$(printf '%s' "$document_content" | sha256sum | cut -d ' ' -f 1)"
document_id="$(docker compose exec -T db psql \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atc \
  "INSERT INTO documents (user_id, title, content, content_sha256) \
   VALUES ($user_id, 'E2E Seed Document', '$document_content', '$content_sha256') \
   RETURNING id")"
if [[ ! "$document_id" =~ ^[0-9]+$ ]]; then
  printf 'Unexpected document id output: %q\n' "$document_id" >&2
  echo "Could not create E2E seed document" >&2
  exit 1
fi

chunk_id="$(docker compose exec -T db psql \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atc \
  "INSERT INTO document_chunks (document_id, chunk_index, content) \
   VALUES ($document_id, 0, '$document_content') \
   RETURNING id")"
if [[ ! "$chunk_id" =~ ^[0-9]+$ ]]; then
  printf 'Unexpected chunk id output: %q\n' "$chunk_id" >&2
  echo "Could not create E2E seed chunk" >&2
  exit 1
fi

{
  echo "E2E_DOCUMENT_ID=$document_id"
  echo "E2E_CHUNK_ID=$chunk_id"
} >> "$GITHUB_ENV"

echo "Seeded full-stack E2E user, document id=$document_id and chunk id=$chunk_id"
