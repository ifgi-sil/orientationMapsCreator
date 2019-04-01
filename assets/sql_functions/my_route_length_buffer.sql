CREATE OR REPLACE FUNCTION my_route_length_buffer(
	param_network regclass,
	param_route regclass,
	param_fraction numeric
)
RETURNS TABLE(
	id integer,
	osm_id bigint,
	osm_name character varying,
	osm_meta character varying,
	osm_source_id bigint,
	osm_target_id bigint,
	clazz integer,
	flags integer,
	source integer,
	target integer,
	km double precision,
	kmh integer,
	cost double precision,
	reverse_cost double precision,
	x1 double precision,
	y1 double precision,
	x2 double precision,
	y2 double precision,
	geom geometry,
	oneway boolean,
	dir character varying
)
AS
$BODY$
DECLARE
	final_query TEXT;
BEGIN
	final_query := FORMAT( $$
		WITH route_length AS
			(SELECT sum(km) FROM %2$s)
		SELECT * FROM %1$s
			WHERE ST_DWithin(
				(SELECT ST_Transform((SELECT ST_Collect(geom) FROM %2$s), 32632)),
				ST_Transform(geom, 32632), (SELECT * FROM route_length)*1000/%3$s
		)$$, param_network, param_route, param_fraction);
	RETURN QUERY EXECUTE final_query;
END;
$BODY$
LANGUAGE PLPGSQL;