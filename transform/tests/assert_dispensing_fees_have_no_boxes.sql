-- Pharmacist dispensing fees are not products: they must carry no box count.

select
    atc_level_1_label,
    sum(n_boxes) as total_boxes
from {{ ref('stg_phmev__dispensing') }}
where is_dispensing_fee
group by 1
having sum(n_boxes) > 0