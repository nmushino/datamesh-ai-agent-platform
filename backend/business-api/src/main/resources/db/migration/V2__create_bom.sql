CREATE TABLE IF NOT EXISTS boms (
    bom_id       VARCHAR(20)  PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    version      VARCHAR(20)  NOT NULL DEFAULT '1.0',
    description  TEXT,
    status       VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bom_components (
    id          BIGSERIAL    PRIMARY KEY,
    bom_id      VARCHAR(20)  NOT NULL REFERENCES boms(bom_id) ON DELETE CASCADE,
    part_number VARCHAR(50)  NOT NULL,
    name        VARCHAR(200) NOT NULL,
    quantity    INTEGER      NOT NULL CHECK (quantity > 0),
    unit        VARCHAR(20)  DEFAULT 'pcs',
    note        TEXT
);

CREATE INDEX idx_boms_product_name ON boms(product_name);
CREATE INDEX idx_bom_components_bom_id ON bom_components(bom_id);
