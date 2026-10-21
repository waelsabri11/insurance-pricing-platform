{#- Volume check: fails if the table row count leaves the expected band
    (catches truncated or duplicated loads). -#}
{% test row_count_between(model, min_rows, max_rows) %}
select n from (select count(*) as n from {{ model }}) t
where n < {{ min_rows }} or n > {{ max_rows }}
{% endtest %}
