CREATE OR REPLACE FUNCTION fn_protect_movimiento()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'Movimiento inmutable. Use tipo=correccion. ID: %', OLD.id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_protect_movimiento
    BEFORE UPDATE OR DELETE ON movimiento
    FOR EACH ROW EXECUTE FUNCTION fn_protect_movimiento();
