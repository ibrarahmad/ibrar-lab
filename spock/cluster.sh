/usr/local/pgsql.16/bin/pg_ctl -D ~/data1/ stop
rm -rf ~/data1
/usr/local/pgsql.16/bin/initdb ~/data1
cp ~/cluster/postgresql.auto.conf1 ~/data1/postgresql.auto.conf
/usr/local/pgsql.16/bin/pg_ctl -D ~/data1/ start -l log1

/usr/local/pgsql.16/bin/pg_ctl -D ~/data2/ stop
rm -rf ~/data2
/usr/local/pgsql.16/bin/initdb ~/data2
cp ~/cluster/postgresql.auto.conf2 ~/data2/postgresql.auto.conf
/usr/local/pgsql.16/bin/pg_ctl -D ~/data2/ start -l log2

/usr/local/pgsql.17/bin/pg_ctl -D ~/data3/ stop
rm -rf ~/data3
/usr/local/pgsql.17/bin/initdb ~/data3
cp ~/cluster/postgresql.auto.conf3 ~/data3/postgresql.auto.conf
/usr/local/pgsql.17/bin/pg_ctl -D ~/data3/ start -l log3
