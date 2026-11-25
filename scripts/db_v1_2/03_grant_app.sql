-- Run as the owner of schema agroscan in the application's database.
-- Replace agro_user if the workstation uses a different PostgreSQL role.
BEGIN;
GRANT USAGE ON SCHEMA agroscan TO agro_user;
GRANT SELECT ON ALL TABLES IN SCHEMA agroscan TO agro_user;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA agroscan TO agro_user;
GRANT INSERT, UPDATE ON agroscan.users, agroscan.products TO agro_user;
GRANT INSERT ON agroscan.inspection_profiles, agroscan.quality_rules,
    agroscan.orders, agroscan.lots, agroscan.boxes, agroscan.audit_logs TO agro_user;
GRANT DELETE ON agroscan.products, agroscan.inspection_profiles,
    agroscan.quality_rules TO agro_user;
GRANT UPDATE ON agroscan.inspections TO agro_user;
GRANT UPDATE (id) ON agroscan.lots, agroscan.inspection_profiles TO agro_user;
GRANT INSERT ON agroscan.inspections, agroscan.inspection_batches,
    agroscan.inspection_images, agroscan.observed_products TO agro_user;
COMMIT;
