-- One-off Snowflake setup for the production target (run as ACCOUNTADMIN or SYSADMIN).
-- Not executed yet: the project runs on DuckDB until a Snowflake account is activated.
-- Cost guardrails: X-Small warehouse, 60 s auto-suspend, and a resource monitor.

create warehouse if not exists PRICING_XS
  warehouse_size = 'XSMALL' auto_suspend = 60 auto_resume = true initially_suspended = true;

create resource monitor if not exists PRICING_MONTHLY with credit_quota = 10
  frequency = monthly start_timestamp = immediately
  triggers on 80 percent do notify on 100 percent do suspend;
alter warehouse PRICING_XS set resource_monitor = PRICING_MONTHLY;

create database if not exists MOTOR_PRICING;
create schema if not exists MOTOR_PRICING.RAW;
create schema if not exists MOTOR_PRICING.MODEL_OUTPUTS;
create schema if not exists MOTOR_PRICING.ANALYTICS;

create role if not exists TRANSFORMER;
grant usage on warehouse PRICING_XS to role TRANSFORMER;
grant usage, create schema on database MOTOR_PRICING to role TRANSFORMER;
grant usage, create table, create view on all schemas in database MOTOR_PRICING to role TRANSFORMER;
grant select on future tables in database MOTOR_PRICING to role TRANSFORMER;

-- Landing: parquet files are PUT to an internal stage (scripts/load_snowflake.py), tables are
-- created from the inferred parquet schema (keeps the source column names, e.g. "IDpol").
create file format if not exists MOTOR_PRICING.RAW.PARQUET_FMT type = parquet;
create stage if not exists MOTOR_PRICING.RAW.LANDING file_format = MOTOR_PRICING.RAW.PARQUET_FMT;
