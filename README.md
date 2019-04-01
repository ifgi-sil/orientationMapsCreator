# orientationMapsCreator
QGIS Plugin to create orientation maps.
This extends the [pgRoutingLayer](https://github.com/pgRouting/pgRoutingLayer) plugin. We only use the `pgr_dijkstra` for route calculation and add functionality to select *Orientation Information* based on the selected route.

## Database setup

This plugin requires a PostgreSQL database to retrieve the input features and save the selected (orientation) features.

Following database specifications are required (see details for setup [here](#osm2po)):
- a routeable network based on [OSM](http://openstreetmap.org/) created with [osm2po](https://osm2po.de/)
- a vertices table created with the pgRouting functions [pgr_createTopology](https://docs.pgrouting.org/latest/en/pgr_createTopology.html?highlight=pgr_createtopology) and [pgr_analyzeGraph](https://docs.pgrouting.org/latest/en/pgr_analyzeGraph.html?highlight=pgr_createtopology); maybe [pgr_createVerticesTable](https://docs.pgrouting.org/latest/en/pgr_createVerticesTable.html?highlight=pgr_createtopology) has to be used instead
- use [pgr_analyzeOneway](https://docs.pgrouting.org/latest/en/pgr_analyzeOneWay.html?highlight=pgr_createtopology) to fill the vertices columns
- make sure that all geometry columns are consistently named `geom`

## Detailed description

### OSM2PO
You can use the [osm2po](http://osm2po.de/) tool to create a routeable street network.

You can configure osm2po in the *osm2po.config* file. e.g. specify to include cycleways or pedestrian ways.

For importing the data to a database, go to the config file and enable `postp.0.class = de.cm.osm2po.plugins.postp.PgRoutingWriter` to get a sql file created. It will create a SQL file in the specified (prefix) directory (default "osm").

Run the tool with
```
java -jar osm2po-core-[version]-signed.jar [file].osm
```

Import the data to the database. Optionally specify schema with
```
ALTER ROLE [db_user] SET search_path TO [schema], public;
```

Remember to reset the default schema again after usage:
```
ALTER ROLE [db_user] SET search_path TO "$user", public, topology;
```

Import sql file into PostGreSQL using psql:
```
sudo -u [db_user] psql -U [db_user] -d [db_name] -q -f [path_to_sql_file]
```

In case you want to move table to a custom schema afterwards run
```
sudo -u [db_user] psql -U [db_user] -d [db_name] -q -c "ALTER TABLE [table] SET SCHEMA [schema]"
```


#### Topology - Vertices table for OSM2PO table

You can use the pgRouting functions [pgr_createTopology](http://docs.pgrouting.org/2.2/en/src/topology/doc/pgr_createTopology.html) and [pgr_analyzeGraph](https://docs.pgrouting.org/2.2/en/src/topology/doc/pgr_analyzeGraph.html) to create a vertices table from the street network table.

Create the vertices table with
```
SELECT  pgr_createTopology('[table]',0.000003,'geom_way');
```

Fill the cnt and chk columns with
```
SELECT  pgr_analyzeGraph('[table]',0.000003,'geom_way');
```

If these functions are not working or generate an empty table, use [pgr_createVerticesTable](https://docs.pgrouting.org/2.4/en/pgr_createVerticesTable.html).
```
SELECT  pgr_createVerticesTable('[table]','geom_way');
```

Eventually use the pgRouting function [pgr_analyzeOneway](https://docs.pgrouting.org/2.0/en/src/common/doc/functions/analyze_oneway.html) to fill the *ein* and *eout* columns for some more advanced network analysis, e.g. analysis of dead ends.
To fill the columns, the table has to be altered.

```
---------- Alter and update table ----------
ALTER TABLE [table] ADD COLUMN oneway boolean;
UPDATE [table] SET oneway = TRUE WHERE cost != reverse_cost;
UPDATE [table] SET oneway = FALSE WHERE cost = reverse_cost;

---------- Update for pgr_analyzeOneway ----------
ALTER TABLE [table] ADD COLUMN dir character varying;
UPDATE [table] SET dir = CASE
	WHEN (cost<1 and reverse_cost>1) THEN 'FT'	-- direction of the LINESSTRING
	WHEN (cost>1 and reverse_cost<1) THEN 'TF'  	-- reverse direction of the LINESTRING
	WHEN (cost<1 and reverse_cost<1) THEN 'B'	-- both ways
	ELSE '' END;					-- unknown

---------- Fill ein and eout columns ----------
SELECT pgr_analyzeOneway('[table]',
  ARRAY['', 'B', 'TF'],
  ARRAY['', 'B', 'FT'],
  ARRAY['', 'B', 'FT'],
  ARRAY['', 'B', 'TF'],
  oneway:='dir');
```



## License

[GPL3](LICENSE)
