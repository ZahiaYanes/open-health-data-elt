-- All antibacterial classes (ATC J01) actually present in the source,
-- with their dispensed volume.
select
    atc.atc_level_4,
    atc.atc_level_4_label,
    count(distinct atc.atc_level_5) as n_substances,
    sum(facts.n_boxes)              as n_boxes
from main_marts.fct_drug_dispensing as facts
join main_marts.dim_atc as atc
    on facts.atc_key = atc.atc_key
where atc.atc_level_2 = 'J01'
  and atc.atc_level_4 is not null
group by 1, 2
order by n_boxes desc