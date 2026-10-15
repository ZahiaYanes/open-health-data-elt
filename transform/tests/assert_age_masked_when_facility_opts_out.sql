-- Disclosure rule derived from the source and verified on all 3.5M rows:
-- when a facility does not report age (facility_reports_age = false),
-- the age band must be masked without exception.

select
    facility_id,
    age_band,
    count(*) as n_rows
from {{ ref('stg_phmev__dispensing') }}
where not facility_reports_age
  and age_band is not null
group by 1, 2