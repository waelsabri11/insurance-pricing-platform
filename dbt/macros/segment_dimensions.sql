{#- Rating dimensions reported in the segment marts. -#}
{% macro segment_dimensions() %}
    {{ return(['driver_age_band', 'vehicle_age_band', 'bonus_malus_band', 'density_band',
               'area_code', 'fuel_type', 'vehicle_brand', 'region_2016']) }}
{% endmacro %}
