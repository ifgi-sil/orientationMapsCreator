DROP FUNCTION IF EXISTS my_route_get_dp(regclass, regclass, regclass, integer);
CREATE OR REPLACE FUNCTION my_route_get_dp(
	param_network regclass,
	param_route regclass,
	param_vertices regclass,
	param_angle integer
)
RETURNS TABLE(
	seq integer,
	id bigint,
	cnt integer,
	chk integer,
	ein integer,
	eout integer,
	geom geometry,
	angle numeric,
	dp_type integer
)
AS
$BODY$
DECLARE
	final_query TEXT;
BEGIN
	final_query :=
		FORMAT( $$
			WITH
			degree2 AS (	-- degree 2
				WITH
				route as (SELECT * FROM %2$s),
				vertices as (SELECT * FROM %3$s),
				intersections AS (
					SELECT
						ST_Transform(v.geom,32632) as intersection,
						v.id as intersection_id,
						(lag(ST_Transform(r.geom,32632),1) OVER(ORDER BY v.seq) ) as lin,
						(lag(v.id,1) OVER(ORDER BY r.seq) ) as lin_id,
						ST_Transform(r.geom,32632) as lout,
						(lag(v.id,-1) OVER(ORDER BY r.seq) ) as lout_id
					FROM
						route r, vertices v
					WHERE
						r._node = v.id
				),
				pnts AS (
					SELECT
						ST_LineInterpolatePoint(lin,abs(ST_LineLocatePoint(lin, intersection) - 0.01)) as pnt_lin,
						ST_LineInterpolatePoint(lout,abs(ST_LineLocatePoint(lout, intersection) - 0.01)) as pnt_lout,
						intersection,intersection_id,lin, lin_id, lout, lout_id
					FROM intersections
				),
				angles AS (
					SELECT
						lin_id, intersection_id, lout_id,
						abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection)
						)::decimal,2)) AS angle_lin,
						abs(round(degrees(
							ST_Azimuth(intersection, pnt_lout)
						)::decimal,2)) AS angle_lout,
						180-abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_lout)
						)::decimal,2)) AS angle_lin_lout
					FROM pnts
				)
				SELECT v.seq,v.id,v.cnt,v.chk,v.ein,v.eout,v.geom,a.angle_lin_lout,
					CASE
						WHEN
							a.angle_lin_lout > %4$s AND a.angle_lin_lout < 180-%4$s	-- lin-lout not straight
						THEN 2	-- turn not at a junction
						ELSE 0
						END as dp_type
				FROM angles as a RIGHT OUTER JOIN vertices as v ON (a.intersection_id = v.id) WHERE v.cnt=2
			),
			degree3 AS (	-- degree 3
				WITH
				network as (SELECT * FROM %1$s),
				route as (SELECT * FROM %2$s),
				vertices as (SELECT * FROM %3$s),
				intersection AS (	-- select vertice of intersection + actual and previous route segments
					SELECT
						ST_Transform(v.geom,32632) as intersection,
						v.id as intersection_id,
						(lag(ST_Transform(r.geom,32632),1) OVER(ORDER BY v.seq) ) as lin,
						(lag(r.id,1) OVER(ORDER BY r.seq) ) as lin_id,
						(lag(r.clazz,1) OVER(ORDER BY r.seq) ) as lin_clazz,
						ST_Transform(r.geom,32632) as lout,
						r.id as lout_id,
						r.clazz as lout_clazz
					FROM
						route r, vertices v
					WHERE
						r._node = v.id
				),
				segments AS (	-- select all street segments from network that connect with intersection
					SELECT
						i.intersection_id, i.intersection, i.lin, i.lin_id, i.lin_clazz, i.lout, i.lout_id, i.lout_clazz,
						n.id as other_id, ST_Transform(n.geom,32632) as other, n.clazz as other_clazz
					FROM
						intersection as i, network as n
					WHERE
						(i.intersection_id = n.source OR i.intersection_id = n.target) AND i.lin_id is not null
				),
				tagged_segments AS (	-- select other street segment that is not part of the route
					SELECT *
					FROM segments
					WHERE other_id not in (SELECT id FROM route)
				),
				pnts AS (	-- calculate points on street segments close to intersection for better angle calculation
					SELECT
						ST_LineInterpolatePoint(lin,abs(ST_LineLocatePoint(lin, intersection) - 0.01)) as pnt_lin,
						ST_LineInterpolatePoint(lout,abs(ST_LineLocatePoint(lout, intersection) - 0.01)) as pnt_lout,
						ST_LineInterpolatePoint(other,abs(ST_LineLocatePoint(other, intersection) - 0.01)) as pnt_other,
						intersection,intersection_id,lin, lin_id, lin_clazz, lout, lout_id, lout_clazz, other, other_id, other_clazz
					FROM tagged_segments
				),
				angles AS (	-- calculate angles (0-180°) between street segments by subtracting individual angles from azimuth
					SELECT
						intersection_id, lin_id, lin_clazz, lout_id, lout_clazz, other_id, other_clazz, lin, lout, other,
						abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection)
						)::decimal,2)) AS angle_lin,
						abs(round(degrees(
							ST_Azimuth(pnt_lout,intersection)
						)::decimal,2)) AS angle_lout,
						abs(round(degrees(
							ST_Azimuth(intersection,pnt_lout)
						)::decimal,2)) AS angle_lout_i,
						abs(round(degrees(
							ST_Azimuth(intersection,pnt_other)
						)::decimal,2)) AS angle_other,
						abs(180-abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_lout)
						)::decimal,2))) AS angle_lin_lout,
						abs(180-abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_other)
						)::decimal,2))) AS angle_lin_other,
						abs(180-abs(round(degrees(
							ST_Azimuth(pnt_lout,intersection) -
							ST_Azimuth(intersection,pnt_other)
						)::decimal,2))) AS angle_lout_other
					FROM pnts
				)
				SELECT v.seq,v.id,v.cnt,v.chk,v.ein,v.eout,v.geom,a.angle_lin_lout,
					CASE
						WHEN
							a.angle_lin_lout > 180-%4$s AND	-- lin-lout relatively straight
							(lin_clazz != lout_clazz OR	-- change in clazz
							lin_clazz >= other_clazz)	-- other segment same or higher clazz
						THEN 1	-- straight on
						WHEN
							(a.angle_lin_lout > %4$s AND a.angle_lin_lout < 180-%4$s) AND	-- lin-lout not straight
							angle_lout_other > 180-%4$s	-- lout-other relatively straight
						THEN 3		-- t-junction
						WHEN
							(a.angle_lin_lout > 30 AND a.angle_lin_lout < 150) AND	-- lin-lout not straight
							angle_lin_other > 150	-- lout-other relatively straight
						THEN 4		-- junction
						ELSE 0
					END as dp_type
				FROM angles as a RIGHT OUTER JOIN vertices as v ON (a.intersection_id = v.id)
				WHERE v.cnt = 3
			),
			degree4 as (	--degree 4
				WITH
				network as (SELECT * FROM %1$s),
				route as (SELECT * FROM %2$s),
				vertices as (SELECT * FROM %3$s),
				intersection AS (	-- select vertice of intersection + actual and previous route segments
					SELECT
						ST_Transform(v.geom,32632) as intersection,
						v.id as intersection_id,
						(lag(ST_Transform(r.geom,32632),1) OVER(ORDER BY v.seq) ) as lin,
						(lag(r.id,1) OVER(ORDER BY r.seq) ) as lin_id,
						(lag(r.clazz,1) OVER(ORDER BY r.seq) ) as lin_clazz,
						ST_Transform(r.geom,32632) as lout,
						r.id as lout_id,
						r.clazz as lout_clazz
					FROM
						route r, vertices v
					WHERE
						r._node = v.id
				),
				segments AS (	-- select all street segments from network that connect with intersection
					SELECT
						i.intersection_id, i.lin_id, i.lout_id, n.id as other_id,
						i.lin_clazz, i.lout_clazz, n.clazz as other_clazz,
						i.intersection, i.lin, i.lout, ST_Transform(n.geom,32632) as other
					FROM
						intersection as i, network as n
					WHERE
						(i.intersection_id = n.source OR i.intersection_id = n.target) AND i.lin_id is not null
				),
				connecting_segments AS (	-- select street segments that are not part of the route
					SELECT *
					FROM segments
					WHERE other_id not in (SELECT id FROM route)
				),
				connecting_segment1 AS (	-- select first of other street segments
					SELECT DISTINCT ON (i.intersection_id) intersection_id, i.lin_id, i.lout_id, i.other_id,
						i.lin_clazz, i.lout_clazz, i.other_clazz,
						i.intersection, i.lin, i.lout, i.other
					FROM connecting_segments as i ORDER BY intersection_id, other_id asc
				),
				connecting_segment2 AS (	-- select last of other street segments
					SELECT DISTINCT ON (i.intersection_id) intersection_id, i.lin_id, i.lout_id, i.other_id,
						i.lin_clazz, i.lout_clazz, i.other_clazz,
						i.intersection, i.lin, i.lout, i.other
					FROM connecting_segments as i ORDER BY intersection_id, other_id desc
				),
				connecting_segment AS (		-- merge together street segments of intersection into rows
					SELECT c1.intersection_id, c1.lin_id, c1.lout_id, c1.other_id as other1_id, c2.other_id as other2_id,
						c1.lin_clazz, c1.lout_clazz, c1.other_clazz as other1_clazz, c2.other_clazz as other2_clazz,
						c1.intersection, c1.lin, c1.lout, c1.other as other1, c2.other as other2
					FROM connecting_segment1 as c1, connecting_segment2 as c2
					WHERE c1.intersection_id=c2.intersection_id
				),
				pnts AS (	-- calculate points on street segments close to intersection for better angle calculation
					SELECT
						ST_LineInterpolatePoint(lin,abs(ST_LineLocatePoint(lin, intersection) - 0.01)) as pnt_lin,
						ST_LineInterpolatePoint(lout,abs(ST_LineLocatePoint(lout, intersection) - 0.01)) as pnt_lout,
						ST_LineInterpolatePoint(other1,abs(ST_LineLocatePoint(other1, intersection) - 0.01)) as pnt_other1,
						ST_LineInterpolatePoint(other2,abs(ST_LineLocatePoint(other2, intersection) - 0.01)) as pnt_other2,
						intersection_id, lin_id, lout_id, other1_id, other2_id,
						lin_clazz, lout_clazz, other1_clazz, other2_clazz,
						intersection,lin, lout, other1, other2
					FROM connecting_segment
				),
				angles AS (	-- calculate angles (0-360°) between street segments by subtracting individual angles from azimuth
					SELECT
						intersection_id, lin_id, lout_id, other1_id, other2_id,
						lin_clazz, lout_clazz, other1_clazz, other2_clazz,
						intersection,lin, lout, other1, other2,
						abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection)
						)::decimal,2)) AS angle_lin,
						abs(round(degrees(
							ST_Azimuth(intersection,pnt_lout)
						)::decimal,2)) AS angle_lout,
						abs(round(degrees(
							ST_Azimuth(intersection,pnt_other1)
						)::decimal,2)) AS angle_other1,
						abs(round(degrees(
							ST_Azimuth(intersection,pnt_other2)
						)::decimal,2)) AS angle_other2,
						mod(180-round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_lout)
						)::decimal,2),360) AS angle_lin_lout,
						mod(180-round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_other1)
						)::decimal,2),360) AS angle_lin_other1,
						mod(180-round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_other2)
						)::decimal,2),360) AS angle_lin_other2,
						abs(180-abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_lout)
						)::decimal,2))) AS angle_lin_lout1
					FROM pnts
				)
				SELECT v.seq,v.id,v.cnt,v.chk,v.ein,v.eout,v.geom,a.angle_lin_lout1,
					CASE
						WHEN
							(a.angle_lin_lout > 180-30 AND a.angle_lin_lout < 180+30) AND			-- lin-lout relatively straight
						 	((angle_lin_other1 < 180-30) OR (angle_lin_other1 > 180+30)) AND	-- lin-other1 not straight
							((angle_lin_other2 < 180-30) OR (angle_lin_other2 > 180+30)) AND	-- lin-other2 not straight
							((angle_lin_other1 < a.angle_lin_lout AND angle_lin_other2 > a.angle_lin_lout) OR
							(angle_lin_other1 > a.angle_lin_lout AND angle_lin_other2 < a.angle_lin_lout)) AND	-- other1 and other2 at opposite sides of lout
							(lin_clazz != lout_clazz OR		-- change in clazz
							lin_clazz >= other1_clazz OR	-- other1 segment same or higher clazz
							lin_clazz >= other2_clazz)		-- other2 segment same or higher clazz
						THEN 1	-- straight on with streets to opposite sides
						WHEN
							(a.angle_lin_lout > 180-30 AND a.angle_lin_lout < 180+30) AND			-- lin-lout relatively straight
						 	((angle_lin_other1 < 180-30) OR (angle_lin_other1 > 180+30)) AND	-- lin-other1 not straight
							((angle_lin_other2 < 180-30) OR (angle_lin_other2 > 180+30)) AND	-- lin-other2 not straight
							((angle_lin_other1 < a.angle_lin_lout AND angle_lin_other2 < a.angle_lin_lout) OR
							(angle_lin_other1 > a.angle_lin_lout AND angle_lin_other2 > a.angle_lin_lout)) AND	-- other1 and other2 at same sides of lout
							(lin_clazz != lout_clazz OR		-- change in clazz
							lin_clazz >= other1_clazz OR	-- other1 segment same or higher clazz
							lin_clazz >= other2_clazz)		-- other2 segment same or higher clazz
						THEN 1	-- straight on with streets at same sides
						WHEN
							((a.angle_lin_lout < 180-30) OR (a.angle_lin_lout > 180+30)) AND	-- lin-lout not straight
							((angle_lin_other1 < a.angle_lin_lout AND angle_lin_other2 < a.angle_lin_lout) OR
							(angle_lin_other1 > a.angle_lin_lout AND angle_lin_other2 > a.angle_lin_lout))	-- other1 and other2 at same side of lout
						THEN 4	-- junction
						ELSE 0
					END as dp_type
				FROM angles as a RIGHT OUTER JOIN vertices as v ON (a.intersection_id = v.id)
				WHERE v.cnt = 4
				ORDER BY v.seq
			),
			degreeX as (	--degree <2 and >4
				WITH
				route as (SELECT * FROM %2$s),
				vertices as (SELECT * FROM %3$s),
				intersections AS (
					SELECT
						ST_Transform(v.geom,32632) as intersection,
						v.id as intersection_id,
						(lag(ST_Transform(r.geom,32632),1) OVER(ORDER BY v.seq) ) as lin,
						(lag(v.id,1) OVER(ORDER BY r.seq) ) as lin_id,
						ST_Transform(r.geom,32632) as lout,
						(lag(v.id,-1) OVER(ORDER BY r.seq) ) as lout_id
					FROM
						route r, vertices v
					WHERE
						r._node = v.id
				),
				pnts AS (
					SELECT
						ST_LineInterpolatePoint(lin,abs(ST_LineLocatePoint(lin, intersection) - 0.01)) as pnt_lin,
						ST_LineInterpolatePoint(lout,abs(ST_LineLocatePoint(lout, intersection) - 0.01)) as pnt_lout,
						intersection,intersection_id,lin, lin_id, lout, lout_id
					FROM intersections
				),
				angles AS (
					SELECT
						lin_id, intersection_id, lout_id,
						abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection)
						)::decimal,2)) AS angle_lin,
						abs(round(degrees(
							ST_Azimuth(intersection, pnt_lout)
						)::decimal,2)) AS angle_lout,
						180-abs(round(degrees(
							ST_Azimuth(pnt_lin,intersection) -
							ST_Azimuth(intersection,pnt_lout)
						)::decimal,2)) AS angle_lin_lout
					FROM pnts
				)
				SELECT v.seq,v.id,v.cnt,v.chk,v.ein,v.eout,v.geom,a.angle_lin_lout, -1 as dp_type
				FROM angles as a RIGHT OUTER JOIN vertices as v ON (a.intersection_id = v.id)
				WHERE v.cnt < 2 OR v.cnt > 4
			)
			SELECT *
			FROM degree2
			UNION
			SELECT *
			FROM degree3
			UNION
			SELECT *
			FROM degree4
			UNION
			SELECT *
			FROM degreeX
		$$, param_network, param_route, param_vertices, param_angle );
	RETURN QUERY EXECUTE final_query;
END;
$BODY$
LANGUAGE PLPGSQL;