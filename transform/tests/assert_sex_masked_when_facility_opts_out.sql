-- Same disclosure rule, applied to sex.

select
    facility_id,
    sex,
    count(*) as n_rows
from {{ ref('stg_phmev__dispensing') }}
where not facility_reports_sex
  and sex is not null
group by 1, 2