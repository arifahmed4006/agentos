-- RBI Circular Intelligence Agent — Supabase Schema
-- Run this in Supabase SQL Editor after enabling pgvector extension

-- 1. Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Documents table
CREATE TABLE public.documents (
    id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    title text,
    url text,
    published_date date,
    created_at timestamp with time zone DEFAULT now(),
    category text,
    full_text text,
    circular_number text,
    summary text,
    applicable_entities text[],
    key_provisions text[],
    effective_date text,
    supersedes_circulars text[],
    amendment_of text,
    references_to text[],
    is_master_direction boolean,
    is_amendment boolean,
    embedded_at timestamp with time zone,
    chunk_strategy text,
    scrape_status text
);

-- 3. Document chunks table
CREATE TABLE public.document_chunks (
    id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    document_id bigint REFERENCES public.documents(id) ON DELETE CASCADE,
    content text,
    embedding vector(1536),
    chunk_index integer,
    title text,
    url text,
    published_date date,
    category text
);

-- 4. Circular relationships table
CREATE TABLE public.circular_relationships (
    id integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    from_document_id integer REFERENCES public.documents(id) ON DELETE CASCADE,
    to_circular_number text,
    relationship_type text,
    created_at timestamp with time zone DEFAULT now()
);

-- 5. Vector similarity index
CREATE INDEX ON public.document_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 6. Hybrid search RPC function
CREATE OR REPLACE FUNCTION public.hybrid_search_rbi(
    query_embedding vector,
    query_text text,
    match_threshold double precision DEFAULT 0.25,
    match_count integer DEFAULT 8,
    filter_category text DEFAULT NULL
)
RETURNS TABLE(
    id bigint,
    document_id bigint,
    content text,
    title text,
    url text,
    published_date date,
    similarity double precision
)
LANGUAGE sql STABLE
AS $$
    WITH scored AS (
        SELECT
            dc.id,
            dc.document_id,
            dc.content,
            dc.title,
            dc.url,
            dc.published_date,
            1 - (dc.embedding <=> query_embedding) AS vector_score,
            COALESCE(ts_rank(
                to_tsvector('english', dc.content || ' ' || dc.title),
                plainto_tsquery('english', query_text)
            ), 0) AS text_score
        FROM document_chunks dc
        WHERE 1 - (dc.embedding <=> query_embedding) > match_threshold
        AND (filter_category IS NULL OR dc.category = filter_category)
    )
    SELECT
        id, document_id, content, title, url, published_date,
        (0.7 * vector_score + 0.3 * LEAST(text_score * 5, 1.0)) AS similarity
    FROM scored
    ORDER BY similarity DESC
    LIMIT match_count;
$$;

-- 7. Enable Row Level Security
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.circular_relationships ENABLE ROW LEVEL SECURITY;
