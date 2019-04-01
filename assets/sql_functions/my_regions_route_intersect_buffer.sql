CREATE OR REPLACE FUNCTION my_regions_route_intersect_buffer(
	param_regions regclass,
	param_route regclass,
	param_buffer float
)
RETURNS TABLE (
	id integer,
	geom geometry,
	land character varying,
	modellart character varying,
	objart character varying,
	objart_txt character varying,
	objid character varying,
	hdu_x integer,
	beginn character varying,
	ende character varying,
	nam character varying,
	rgs character varying,
	bemerkung character varying
)
AS
$BODY$
DECLARE
	final_query TEXT;
BEGIN
	final_query := FORMAT( $$
		WITH route_length AS
			(SELECT sum(km) FROM %2$s)
		SELECT DISTINCT(regions.*)
		FROM %1$s as regions
		WHERE ST_DWithin(
				(SELECT ST_Transform((SELECT ST_Collect(geom) FROM %2$s), 32632)),
				ST_Transform(geom, 32632), %3$s)
		$$, param_regions, param_route, param_buffer);
	RETURN QUERY EXECUTE final_query;
END;
$BODY$
LANGUAGE PLPGSQL;