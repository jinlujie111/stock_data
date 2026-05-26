
1：xxljob mysql账号密码
mysql -h localhost -P 3306 -u xxljob -p'1qaz!QAZjinlujie' -D xxl_job

2：xxljob后台启动

path_pwd='1qaz!QAZjinlujie'
path_token='xxljob1qaz!QAZjinlujie'

cd /opt/xxl-job/run
nohup java -jar xxl-job-admin-*.jar \
  --spring.datasource.url="jdbc:mysql://127.0.0.1:3306/xxl_job?useUnicode=true&characterEncoding=UTF-8&autoReconnect=true&serverTimezone=Asia/Shanghai" \
  --spring.datasource.username=xxljob \
  --spring.datasource.password=${path_pwd} \
  --xxl.job.accessToken=${path_token} \
  > admin.log 2>&1 &

tail -50f admin.log

3：xxljob网页端
http://http://120.26.103.34:8080/xxl-job-admin
（默认账号 admin / jinlujie）

4:stock数据库账号密码：
mysql -h localhost -P 3306 -u app_user -pjinlujie -D stock_data

4:root数据库账号密码：
mysql -h localhost -P 3306 -u root -pjinlujie

5：python环境地址
 alias python='/usr/local/bin/python3.11'

6:config配置库
mysql -h localhost -P 3306 -u data_config -p'1qaz!QAZjinlujie' -D data_config

