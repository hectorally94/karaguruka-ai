CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  filename text NOT NULL,
  mime text NOT NULL,
  size_bytes integer NOT NULL,
  file bytea NOT NULL,
  category text NOT NULL DEFAULT 'Général',
  audience text NOT NULL DEFAULT 'public' CHECK (audience IN ('public', 'internal')),
  status text NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'failed')),
  error text,
  active boolean NOT NULL DEFAULT true,
  effective_from date,
  expires_at date,
  version integer NOT NULL DEFAULT 1,
  page_count integer,
  chunk_count integer NOT NULL DEFAULT 0,
  used_ocr boolean NOT NULL DEFAULT false,
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page integer,
  ordinal integer NOT NULL,
  content text NOT NULL,
  tsv tsvector NOT NULL,
  embedding vector(1024)
);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks(document_id);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel text NOT NULL DEFAULT 'text' CHECK (channel IN ('text', 'voice')),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'transferred')),
  flow jsonb,
  primary_intent text,
  sentiment text NOT NULL DEFAULT 'neutre',
  is_example boolean NOT NULL DEFAULT false,
  started_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  id bigserial PRIMARY KEY,
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('user', 'assistant', 'agent')),
  content text NOT NULL,
  intent text,
  sources jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages(conversation_id, id);

CREATE SEQUENCE IF NOT EXISTS ticket_ref_seq;
CREATE TABLE IF NOT EXISTS tickets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ref text NOT NULL UNIQUE DEFAULT ('KAR-' || lpad(nextval('ticket_ref_seq')::text, 5, '0')),
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  kind text NOT NULL,
  department text NOT NULL,
  priority text NOT NULL CHECK (priority IN ('P1', 'P2', 'P3')),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved')),
  summary text NOT NULL,
  contact text,
  data jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  taken_at timestamptz,
  resolved_at timestamptz
);
CREATE INDEX IF NOT EXISTS tickets_status_idx ON tickets(status, priority, created_at);

CREATE TABLE IF NOT EXISTS unanswered_questions (
  id bigserial PRIMARY KEY,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  question text NOT NULL,
  dismissed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
