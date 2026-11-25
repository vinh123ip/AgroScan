-- AgroScan Database Design v1.2 | PostgreSQL 17+ | Run once in the target database.
-- One transaction. An existing agroscan schema causes a safe stop; public is untouched.
BEGIN;
CREATE SCHEMA agroscan;
SET LOCAL search_path TO agroscan, pg_catalog;

CREATE TABLE users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login text NOT NULL UNIQUE CHECK (btrim(login) <> ''),
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('admin','inspector','manager')),
    can_review boolean NOT NULL DEFAULT false,
    active boolean NOT NULL DEFAULT true,
    CHECK (NOT can_review OR role = 'inspector')
);

CREATE TABLE products (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    category text NOT NULL
);

CREATE TABLE inspection_profiles (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES products,
    version integer NOT NULL CHECK (version > 0),
    reference text NOT NULL CHECK (btrim(reference) <> ''),
    approved boolean NOT NULL DEFAULT false,
    applicability jsonb NOT NULL CHECK (jsonb_typeof(applicability) = 'object'),
    retired_at timestamptz,
    UNIQUE (product_id, version)
);

CREATE TABLE quality_rules (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id bigint NOT NULL REFERENCES inspection_profiles,
    code text NOT NULL,
    rule_type text NOT NULL,
    operator text,
    limit_ratio numeric,
    source_clause text NOT NULL CHECK (btrim(source_clause) <> ''),
    UNIQUE (profile_id, code),
    CHECK ((rule_type = 'exclusion' AND operator IS NULL AND limit_ratio IS NULL)
        OR (rule_type = 'ratio' AND operator IS NOT NULL AND operator IN ('gt','ge')
            AND limit_ratio IS NOT NULL AND limit_ratio BETWEEN 0 AND 1))
);

CREATE TABLE sampling_rules (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    edition text NOT NULL,
    level_code text NOT NULL,
    aql numeric NOT NULL CHECK (aql > 0 AND aql <> 'NaN'),
    n_min integer NOT NULL CHECK (n_min > 0),
    n_max integer NOT NULL CHECK (n_max >= n_min),
    sample_n integer NOT NULL CHECK (sample_n BETWEEN 1 AND n_min),
    ac integer NOT NULL CHECK (ac >= 0),
    re integer NOT NULL CHECK (re = ac::bigint + 1 AND re <= sample_n),
    verification jsonb NOT NULL CHECK (jsonb_typeof(verification) = 'object'),
    UNIQUE (edition, level_code, aql, n_min, n_max)
);

CREATE TABLE orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code text NOT NULL UNIQUE,
    supplier text,
    customer text,
    source_file text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES orders,
    profile_id bigint NOT NULL REFERENCES inspection_profiles,
    sampling_rule_id bigint REFERENCES sampling_rules,
    lot_code text NOT NULL,
    declared_boxes integer NOT NULL CHECK (declared_boxes > 0),
    container_ref text,
    plan_snapshot jsonb CHECK (jsonb_typeof(plan_snapshot) = 'object'),
    locked_at timestamptz,
    UNIQUE (order_id, lot_code),
    CHECK ((locked_at IS NULL AND plan_snapshot IS NULL)
        OR (locked_at IS NOT NULL AND sampling_rule_id IS NOT NULL AND plan_snapshot IS NOT NULL))
);

CREATE TABLE boxes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_id bigint NOT NULL REFERENCES lots,
    box_code text NOT NULL,
    scan_token uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    UNIQUE (lot_id, box_code)
);

CREATE TABLE sample_selections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    box_id bigint NOT NULL REFERENCES boxes,
    slot_no integer NOT NULL CHECK (slot_no > 0),
    replaces_id bigint UNIQUE REFERENCES sample_selections,
    plan_version integer NOT NULL CHECK (plan_version > 0),
    reason text,
    selected_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (box_id, plan_version),
    CHECK (replaces_id IS NULL OR (replaces_id <> id AND nullif(btrim(reason), '') IS NOT NULL))
);

CREATE TABLE inspections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    selection_id bigint NOT NULL REFERENCES sample_selections,
    previous_id bigint UNIQUE REFERENCES inspections,
    inspector_id bigint NOT NULL REFERENCES users,
    reviewer_id bigint REFERENCES users,
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    station_code text NOT NULL CHECK (btrim(station_code) <> ''),
    state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','submitted','reviewed','reinspect')),
    ai_versions jsonb NOT NULL CHECK (jsonb_typeof(ai_versions) = 'object'),
    submitted_at timestamptz,
    reviewed_at timestamptz,
    box_result text CHECK (box_result IN ('conforming','nonconforming')),
    review_note text,
    coverage jsonb CHECK (jsonb_typeof(coverage) = 'object'),
    checkpoint jsonb CHECK (jsonb_typeof(checkpoint) = 'object'),
    machine_box_result jsonb CHECK (jsonb_typeof(machine_box_result) = 'object'),
    UNIQUE (selection_id, attempt_no),
    CHECK ((attempt_no = 1) = (previous_id IS NULL)),
    CHECK (reviewer_id IS NULL OR reviewer_id <> inspector_id),
    CHECK ((state = 'draft') = (submitted_at IS NULL)),
    CHECK ((state IN ('reviewed','reinspect')) = (reviewer_id IS NOT NULL)),
    CHECK ((state IN ('reviewed','reinspect')) = (reviewed_at IS NOT NULL)),
    CHECK ((state = 'reviewed') = (box_result IS NOT NULL)),
    CHECK (state NOT IN ('reviewed','reinspect') OR nullif(btrim(review_note),'') IS NOT NULL),
    CHECK (reviewed_at >= submitted_at)
);

CREATE TABLE inspection_batches (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inspection_id bigint NOT NULL REFERENCES inspections,
    batch_no integer NOT NULL CHECK (batch_no > 0),
    coverage_note text,
    UNIQUE (inspection_id, batch_no)
);

CREATE TABLE inspection_images (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id bigint NOT NULL REFERENCES inspection_batches,
    is_count_image boolean NOT NULL,
    object_key text NOT NULL UNIQUE CHECK (btrim(object_key) <> ''),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    width_px integer NOT NULL CHECK (width_px > 0),
    height_px integer NOT NULL CHECK (height_px > 0),
    captured_at timestamptz,
    annotated_key text,
    source_kind text NOT NULL CHECK (source_kind IN ('camera','imported_image')),
    usage_context text NOT NULL CHECK (usage_context IN ('demo','operational')),
    received_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_kind <> 'camera' OR captured_at IS NOT NULL)
);
CREATE UNIQUE INDEX one_count_image ON inspection_images(batch_id) WHERE is_count_image;

CREATE TABLE observed_products (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id bigint NOT NULL REFERENCES inspection_batches,
    count_image_id bigint NOT NULL REFERENCES inspection_images,
    unit_no integer NOT NULL CHECK (unit_no > 0),
    x integer NOT NULL CHECK (x >= 0),
    y integer NOT NULL CHECK (y >= 0),
    width integer NOT NULL CHECK (width > 0),
    height integer NOT NULL CHECK (height > 0),
    ai_findings jsonb NOT NULL CHECK (jsonb_typeof(ai_findings) = 'array'),
    review_findings jsonb CHECK (jsonb_typeof(review_findings) = 'array'),
    warning text NOT NULL CHECK (warning IN ('green','yellow','red')),
    counted boolean NOT NULL DEFAULT true,
    UNIQUE (batch_id, unit_no)
);

CREATE TABLE lot_decisions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_id bigint NOT NULL REFERENCES lots,
    reviewer_id bigint NOT NULL REFERENCES users,
    version integer NOT NULL CHECK (version > 0),
    outcome text NOT NULL CHECK (outcome IN ('approve','reject')),
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    manifest_bytes bytea NOT NULL CHECK (octet_length(manifest_bytes) > 0),
    signature bytea NOT NULL CHECK (octet_length(signature) > 0),
    certificate_der bytea NOT NULL CHECK (octet_length(certificate_der) > 0),
    signed_at timestamptz NOT NULL,
    UNIQUE (lot_id, version)
);

CREATE TABLE audit_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id bigint REFERENCES users,
    action text NOT NULL CHECK (btrim(action) <> ''),
    target_type text NOT NULL,
    target_key text NOT NULL,
    details jsonb NOT NULL CHECK (jsonb_typeof(details) = 'object'),
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX lots_profile ON lots(profile_id);
CREATE INDEX lots_lookup ON lots(sampling_rule_id);
CREATE INDEX inspections_queue ON inspections(state, submitted_at) WHERE state = 'submitted';
CREATE INDEX inspections_creator ON inspections(inspector_id);
CREATE INDEX inspections_reviewer ON inspections(reviewer_id) WHERE reviewer_id IS NOT NULL;
CREATE INDEX observations_image ON observed_products(count_image_id);
CREATE INDEX images_batch ON inspection_images(batch_id);
CREATE INDEX decisions_signer ON lot_decisions(reviewer_id);
CREATE INDEX audit_target ON audit_logs(target_type, target_key, action, id DESC);
CREATE INDEX audit_actor ON audit_logs(actor_id, occurred_at);
CREATE UNIQUE INDEX inference_execution ON audit_logs(target_key, (details->>'execution_id'))
    WHERE action = 'inference_result' AND target_type = 'image';
CREATE UNIQUE INDEX one_submission_event ON audit_logs(target_key)
    WHERE action = 'inspection_submitted' AND target_type = 'inspection';

CREATE VIEW current_selections AS
SELECT s.* FROM sample_selections s
JOIN boxes b ON b.id = s.box_id
JOIN lots l ON l.id = b.lot_id
WHERE s.plan_version = (l.plan_snapshot->>'active_version')::integer
  AND NOT EXISTS (SELECT FROM sample_selections r WHERE r.replaces_id = s.id);

CREATE VIEW latest_lot_decisions AS
SELECT DISTINCT ON (lot_id) * FROM lot_decisions ORDER BY lot_id, version DESC;

CREATE FUNCTION retain_history() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Historical record in % is immutable; append a new version or audit event', TG_TABLE_NAME;
END $$;

CREATE TRIGGER retain_images BEFORE UPDATE OR DELETE ON inspection_images
FOR EACH ROW EXECUTE FUNCTION retain_history();
CREATE TRIGGER retain_audit BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION retain_history();
CREATE TRIGGER retain_decisions BEFORE UPDATE OR DELETE ON lot_decisions
FOR EACH ROW EXECUTE FUNCTION retain_history();
CREATE TRIGGER retain_selections BEFORE UPDATE OR DELETE ON sample_selections
FOR EACH ROW EXECUTE FUNCTION retain_history();
CREATE TRIGGER retain_attempts BEFORE DELETE ON inspections
FOR EACH ROW EXECUTE FUNCTION retain_history();
CREATE TRIGGER retain_lookup BEFORE UPDATE OR DELETE ON sampling_rules
FOR EACH ROW EXECUTE FUNCTION retain_history();


-- Profile rules are editable while drafting. Approval freezes their contents.
CREATE FUNCTION guard_profile() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.approved AND
       ((to_jsonb(NEW) - 'retired_at') <> (to_jsonb(OLD) - 'retired_at')
        OR (OLD.retired_at IS NOT NULL AND NEW.retired_at IS DISTINCT FROM OLD.retired_at)) THEN
        RAISE EXCEPTION 'Approved profile is immutable except for retirement';
    END IF;
    IF NEW.approved AND (TG_OP = 'INSERT' OR NOT OLD.approved) THEN
        IF NOT EXISTS (SELECT FROM quality_rules WHERE profile_id = NEW.id)
           OR NOT (NEW.applicability ?& ARRAY['form','source_edition']) THEN
            RAISE EXCEPTION 'Approval requires rules, product form and source edition';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER protect_profile BEFORE INSERT OR UPDATE ON inspection_profiles
FOR EACH ROW EXECUTE FUNCTION guard_profile();

CREATE FUNCTION guard_rule() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.profile_id <> OLD.profile_id THEN
        RAISE EXCEPTION 'Create a new rule in the target profile';
    END IF;
    IF (SELECT approved FROM inspection_profiles
        WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.profile_id ELSE NEW.profile_id END FOR UPDATE) THEN
        RAISE EXCEPTION 'Create a new profile version before changing approved rules';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER protect_rule BEFORE INSERT OR UPDATE OR DELETE ON quality_rules
FOR EACH ROW EXECUTE FUNCTION guard_rule();

-- Digest over the ordered physical register, including its external scan tokens.
CREATE FUNCTION register_digest(p_lot bigint) RETURNS text
LANGUAGE sql STABLE SET search_path = agroscan, pg_catalog AS $$
    SELECT encode(sha256(convert_to(coalesce(jsonb_agg(jsonb_build_array(id, box_code, scan_token)
        ORDER BY id), '[]'::jsonb)::text, 'UTF8')), 'hex') FROM boxes WHERE lot_id = p_lot
$$;

CREATE FUNCTION guard_plan() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE
    rule sampling_rules;
    rev jsonb;
    revisions jsonb;
    v integer;
    picked integer;
BEGIN
    IF TG_OP = 'INSERT' OR NEW.profile_id IS DISTINCT FROM OLD.profile_id THEN
        IF NOT EXISTS (SELECT FROM inspection_profiles WHERE id = NEW.profile_id
                       AND approved AND retired_at IS NULL FOR SHARE) THEN
            RAISE EXCEPTION 'New lots require an approved, non-retired profile';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.locked_at IS NOT NULL THEN
        IF NEW.locked_at IS DISTINCT FROM OLD.locked_at
           OR (NEW.id, NEW.profile_id, NEW.order_id, NEW.lot_code)
              IS DISTINCT FROM (OLD.id, OLD.profile_id, OLD.order_id, OLD.lot_code) THEN
            RAISE EXCEPTION 'Locked lot identity and criteria must be preserved';
        END IF;
        IF (NEW.plan_snapshot, NEW.sampling_rule_id, NEW.declared_boxes)
           IS NOT DISTINCT FROM (OLD.plan_snapshot, OLD.sampling_rule_id, OLD.declared_boxes) THEN
            RETURN NEW;
        END IF;
    END IF;
    IF NEW.locked_at IS NULL THEN RETURN NEW; END IF;
    revisions := NEW.plan_snapshot->'revisions';
    v := (NEW.plan_snapshot->>'active_version')::integer;
    IF jsonb_typeof(revisions) IS DISTINCT FROM 'array' OR v IS NULL OR v < 1
       OR jsonb_array_length(revisions) <> v THEN
        RAISE EXCEPTION 'Active version must identify the last revision';
    END IF;
    rev := revisions->-1;
    IF TG_OP = 'UPDATE' AND OLD.locked_at IS NOT NULL THEN
        IF (revisions - (v-1)) IS DISTINCT FROM OLD.plan_snapshot->'revisions'
           OR (rev->>'prior_version')::integer IS DISTINCT FROM v-1
           OR nullif(btrim(rev->>'reason'),'') IS NULL
           OR nullif(btrim(rev->>'open_attempt_disposition'),'') IS NULL THEN
            RAISE EXCEPTION 'Append one revision with its predecessor, reason and attempt disposition';
        END IF;
    ELSIF v <> 1 THEN
        RAISE EXCEPTION 'First locked plan must be revision 1';
    END IF;
    SELECT * INTO STRICT rule FROM sampling_rules WHERE id = NEW.sampling_rule_id;
    IF (rule.verification->>'status') IS DISTINCT FROM 'verified'
       OR NEW.declared_boxes NOT BETWEEN rule.n_min AND rule.n_max
       OR (SELECT count(*) FROM boxes WHERE lot_id = NEW.id) <> NEW.declared_boxes
       OR NOT (rev @> jsonb_build_object('version',v,'N',NEW.declared_boxes,
           'level',rule.level_code,'aql',rule.aql,'lookup_table',rule.edition,'lookup_cell',rule.id,
           'n',rule.sample_n,'Ac',rule.ac,'Re',rule.re,'register_sha256',register_digest(NEW.id)))
       OR NOT (rev ?& ARRAY['seed','algorithm_version','selected_box_ids'])
       OR nullif(rev->>'seed','') IS NULL OR nullif(rev->>'algorithm_version','') IS NULL
       OR jsonb_typeof(rev->'selected_box_ids') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Plan does not match the verified lookup and confirmed register';
    END IF;
    SELECT count(DISTINCT b.id) INTO picked
    FROM jsonb_array_elements(rev->'selected_box_ids') e
    JOIN boxes b ON to_jsonb(b.id) = e.value AND b.lot_id = NEW.id;
    IF picked <> rule.sample_n OR jsonb_array_length(rev->'selected_box_ids') <> picked THEN
        RAISE EXCEPTION 'Plan must identify exactly n distinct registered boxes';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER protect_plan BEFORE INSERT OR UPDATE ON lots
FOR EACH ROW EXECUTE FUNCTION guard_plan();

CREATE FUNCTION lock_register() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (NEW.id, NEW.lot_id) <> (OLD.id, OLD.lot_id) THEN
        RAISE EXCEPTION 'Box identity and lot are permanent';
    END IF;
    PERFORM FROM lots WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.lot_id ELSE NEW.lot_id END FOR UPDATE;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER lock_box_register BEFORE INSERT OR UPDATE OR DELETE ON boxes
FOR EACH ROW EXECUTE FUNCTION lock_register();

CREATE FUNCTION validate_register_at_commit() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE l lots;
BEGIN
    SELECT * INTO l FROM lots WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.lot_id ELSE NEW.lot_id END;
    IF l.locked_at IS NOT NULL AND
       (l.plan_snapshot->'revisions'->-1->>'register_sha256') IS DISTINCT FROM register_digest(l.id) THEN
        RAISE EXCEPTION 'Update the sampling revision in the same transaction as the locked register';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER check_register AFTER INSERT OR UPDATE OR DELETE ON boxes
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_register_at_commit();

CREATE FUNCTION guard_selection() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE l lots; rev jsonb; original_id bigint;
BEGIN
    SELECT p.* INTO STRICT l FROM lots p JOIN boxes b ON b.lot_id = p.id
      WHERE b.id = NEW.box_id FOR UPDATE OF p;
    rev := l.plan_snapshot->'revisions'->-1;
    IF NEW.plan_version IS DISTINCT FROM (rev->>'version')::integer
       OR NEW.slot_no NOT BETWEEN 1 AND (rev->>'n')::integer THEN
        RAISE EXCEPTION 'Selection must belong to an active sample slot';
    END IF;
    original_id := (rev->'selected_box_ids'->>(NEW.slot_no-1))::bigint;
    IF NEW.replaces_id IS NULL THEN
        IF NEW.box_id <> original_id THEN RAISE EXCEPTION 'Box does not match the sampled slot'; END IF;
    ELSIF EXISTS (SELECT FROM inspections WHERE selection_id = NEW.replaces_id)
       OR (rev->'selected_box_ids') @> jsonb_build_array(NEW.box_id)
       OR NOT EXISTS (SELECT FROM current_selections s JOIN boxes b ON b.id = s.box_id
           WHERE s.id = NEW.replaces_id AND s.slot_no = NEW.slot_no AND b.lot_id = l.id) THEN
        RAISE EXCEPTION 'Replacement requires an uninspected current slot and an eligible spare box';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER check_selection BEFORE INSERT ON sample_selections
FOR EACH ROW EXECUTE FUNCTION guard_selection();

CREATE FUNCTION check_replacement_event() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
BEGIN
    IF NOT EXISTS (SELECT FROM audit_logs a JOIN users u ON u.id = a.actor_id
        WHERE a.action = 'replacement_authorized' AND a.target_type = 'selection' AND a.target_key = NEW.id::text
        AND u.active AND u.can_review AND a.details->>'transaction_id' = pg_current_xact_id()::text
        AND a.details @> jsonb_build_object('reason',NEW.reason,'replaces_id',NEW.replaces_id)) THEN
        RAISE EXCEPTION 'Replacement requires an attributable Reviewer authorization';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER replacement_event AFTER INSERT ON sample_selections
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.replaces_id IS NOT NULL)
EXECUTE FUNCTION check_replacement_event();


-- Serialize evidence changes and submission on the same inspection row.
CREATE FUNCTION guard_evidence() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE attempt_id bigint; phase text; picture inspection_images;
BEGIN
    IF TG_TABLE_NAME = 'inspection_batches' THEN
        IF TG_OP = 'UPDATE' AND (NEW.id, NEW.inspection_id) <> (OLD.id, OLD.inspection_id) THEN
            RAISE EXCEPTION 'Batch cannot be reassigned';
        END IF;
        attempt_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.inspection_id ELSE NEW.inspection_id END;
    ELSE
        IF TG_OP = 'UPDATE' AND NEW.batch_id <> OLD.batch_id THEN
            RAISE EXCEPTION 'Evidence cannot be reassigned to another batch';
        END IF;
        SELECT inspection_id INTO STRICT attempt_id FROM inspection_batches
        WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.batch_id ELSE NEW.batch_id END;
    END IF;
    SELECT state INTO STRICT phase FROM inspections WHERE id = attempt_id FOR UPDATE;
    IF phase <> 'draft' THEN
        IF phase = 'submitted' AND TG_TABLE_NAME = 'observed_products' AND TG_OP = 'UPDATE' THEN
            IF (to_jsonb(NEW) - 'review_findings') = (to_jsonb(OLD) - 'review_findings') THEN
                RETURN NEW;
            END IF;
        END IF;
        RAISE EXCEPTION 'Original evidence is frozen after submission';
    END IF;
    IF TG_TABLE_NAME = 'observed_products' AND TG_OP <> 'DELETE' THEN
        IF NEW.review_findings IS NOT NULL THEN RAISE EXCEPTION 'Review corrections require a submitted attempt'; END IF;
        SELECT * INTO STRICT picture FROM inspection_images WHERE id = NEW.count_image_id;
        IF picture.batch_id <> NEW.batch_id OR NOT picture.is_count_image
           OR NEW.x::bigint + NEW.width > picture.width_px OR NEW.y::bigint + NEW.height > picture.height_px THEN
            RAISE EXCEPTION 'Observation must fit the count image of its own batch';
        END IF;
    END IF;
    IF TG_TABLE_NAME = 'inspection_batches' AND TG_OP IN ('INSERT','DELETE') THEN
        UPDATE inspections SET coverage = NULL WHERE id = attempt_id AND coverage IS NOT NULL;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER protect_batches BEFORE INSERT OR UPDATE OR DELETE ON inspection_batches
FOR EACH ROW EXECUTE FUNCTION guard_evidence();
CREATE TRIGGER check_image_attempt BEFORE INSERT ON inspection_images
FOR EACH ROW EXECUTE FUNCTION guard_evidence();
CREATE TRIGGER protect_observations BEFORE INSERT OR UPDATE OR DELETE ON observed_products
FOR EACH ROW EXECUTE FUNCTION guard_evidence();

-- Count each physical unit once for each rule, even if the AI repeats a finding.
CREATE VIEW box_rule_counts AS
SELECT i.id AS inspection_id, q.code, q.rule_type, q.operator, q.limit_ratio,
       count(DISTINCT o.id) AS denominator,
       count(DISTINCT o.id) FILTER (
           WHERE o.ai_findings @> jsonb_build_array(jsonb_build_object('code',q.code,'assessment','present'))
       ) AS machine_affected,
       count(DISTINCT o.id) FILTER (
           WHERE coalesce(o.review_findings,o.ai_findings) @>
                 jsonb_build_array(jsonb_build_object('code',q.code,'assessment','present'))
       ) AS reviewed_affected
FROM inspections i JOIN sample_selections s ON s.id = i.selection_id
JOIN boxes b ON b.id = s.box_id JOIN lots l ON l.id = b.lot_id
JOIN quality_rules q ON q.profile_id = l.profile_id
LEFT JOIN inspection_batches g ON g.inspection_id = i.id
LEFT JOIN observed_products o ON o.batch_id = g.id AND o.counted
GROUP BY i.id, q.id;

CREATE FUNCTION guard_attempt() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE physical_box bigint; expected_batches jsonb; violates_rule boolean; unresolved boolean;
BEGIN
    SELECT b.id INTO STRICT physical_box FROM lots p JOIN boxes b ON b.lot_id = p.id
    JOIN sample_selections s ON s.box_id = b.id WHERE s.id = NEW.selection_id FOR UPDATE OF p;
    IF NOT EXISTS (SELECT FROM current_selections WHERE id = NEW.selection_id) THEN
        RAISE EXCEPTION 'Attempt is outside the active sample';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' OR NOT EXISTS (SELECT FROM users WHERE id = NEW.inspector_id
                                               AND active AND role = 'inspector' FOR SHARE) THEN
            RAISE EXCEPTION 'An active inspector must open a draft attempt';
        END IF;
        IF NEW.previous_id IS NOT NULL AND NOT EXISTS (SELECT FROM inspections p WHERE p.id = NEW.previous_id
            AND p.selection_id = NEW.selection_id AND p.attempt_no = NEW.attempt_no-1 AND p.state = 'reinspect') THEN
            RAISE EXCEPTION 'Reinspection must follow the preceding attempt on the same selection';
        END IF;
        RETURN NEW;
    END IF;
    IF (NEW.id,NEW.selection_id,NEW.attempt_no,NEW.previous_id,NEW.inspector_id)
       IS DISTINCT FROM (OLD.id,OLD.selection_id,OLD.attempt_no,OLD.previous_id,OLD.inspector_id) THEN
        RAISE EXCEPTION 'Attempt identity and original inspector are immutable';
    END IF;
    IF OLD.state IN ('reviewed','reinspect') THEN RAISE EXCEPTION 'Resolved attempt is immutable'; END IF;
    IF OLD.state = 'submitted' THEN
        IF NEW.state NOT IN ('reviewed','reinspect')
           OR (to_jsonb(NEW) - ARRAY['state','reviewer_id','reviewed_at','box_result','review_note'])
              <> (to_jsonb(OLD) - ARRAY['state','reviewer_id','reviewed_at','box_result','review_note']) THEN
            RAISE EXCEPTION 'Only the independent review may change a submitted attempt';
        END IF;
        IF NOT EXISTS (SELECT FROM users WHERE id = NEW.reviewer_id AND active AND can_review FOR SHARE)
           OR EXISTS (SELECT FROM inspections p JOIN sample_selections s ON s.id = p.selection_id
               LEFT JOIN audit_logs a ON a.target_type = 'inspection' AND a.target_key = p.id::text
                                     AND a.action = 'inspection_submitted'
               WHERE s.box_id = physical_box AND NEW.reviewer_id IN (p.inspector_id, a.actor_id)) THEN
            RAISE EXCEPTION 'Reviewer must be authorized and independent of attempts on this box';
        END IF;
    ELSIF NEW.state = 'submitted' THEN
        SELECT jsonb_agg(id ORDER BY id) INTO expected_batches FROM inspection_batches WHERE inspection_id = NEW.id;
        IF expected_batches IS NULL OR NEW.coverage IS NULL
           OR NOT (NEW.coverage @> jsonb_build_object('confirmed',true,'inspector_id',NEW.inspector_id))
           OR (NEW.coverage->>'confirmed_at')::timestamptz IS NULL
           OR (NEW.coverage->>'confirmed_at')::timestamptz > NEW.submitted_at
           OR jsonb_typeof(NEW.coverage->'batch_ids') IS DISTINCT FROM 'array'
           OR NOT ((NEW.coverage->'batch_ids') @> expected_batches)
           OR jsonb_array_length(NEW.coverage->'batch_ids') <> jsonb_array_length(expected_batches)
           OR NOT coalesce(NEW.machine_box_result ?& ARRAY['class_counts','denominator','comparisons','exclusions','outcome'],false)
           OR jsonb_typeof(NEW.machine_box_result->'class_counts') IS DISTINCT FROM 'object'
           OR jsonb_typeof(NEW.machine_box_result->'comparisons') IS DISTINCT FROM 'array'
           OR jsonb_typeof(NEW.machine_box_result->'exclusions') IS DISTINCT FROM 'array'
           OR coalesce(NEW.machine_box_result->>'outcome','') NOT IN ('conforming','nonconforming','needs_review')
           OR EXISTS (SELECT FROM inspection_batches g WHERE g.inspection_id = NEW.id AND NOT EXISTS
               (SELECT FROM observed_products o WHERE o.batch_id = g.id AND o.counted)) THEN
            RAISE EXCEPTION 'Submission requires whole-box confirmation, count evidence for every batch and a frozen result';
        END IF;
        IF NEW.machine_box_result->>'outcome' <> 'needs_review' AND EXISTS (
            SELECT FROM inspection_batches g JOIN inspection_images im ON im.batch_id=g.id AND im.is_count_image
            WHERE g.inspection_id=NEW.id AND (
                NOT EXISTS (SELECT FROM audit_logs a WHERE a.action='inference_result' AND a.target_type='image'
                            AND a.target_key=im.id::text)
                OR EXISTS (SELECT FROM (SELECT DISTINCT ON (a.details->>'stage') a.details
                    FROM audit_logs a WHERE a.action='inference_result' AND a.target_type='image' AND a.target_key=im.id::text
                    ORDER BY a.details->>'stage', a.id DESC) latest
                    WHERE latest.details->>'validation' IS DISTINCT FROM 'valid'))) THEN
            RAISE EXCEPTION 'Missing or invalid inference requires review';
        END IF;
        SELECT EXISTS (SELECT FROM box_rule_counts r WHERE r.inspection_id=NEW.id AND (
            (r.rule_type='exclusion' AND r.machine_affected > 0)
            OR (r.operator='gt' AND r.machine_affected > r.limit_ratio * r.denominator)
            OR (r.operator='ge' AND r.machine_affected >= r.limit_ratio * r.denominator))) INTO violates_rule;
        SELECT EXISTS (SELECT FROM inspection_batches g JOIN observed_products o ON o.batch_id=g.id
            WHERE g.inspection_id=NEW.id AND o.counted AND (o.ai_findings @> '[{"assessment":"uncertain"}]'
            OR jsonb_array_length(o.ai_findings) <> (SELECT count(*) FROM box_rule_counts r
                                                      WHERE r.inspection_id=NEW.id))) INTO unresolved;
        IF (NEW.machine_box_result->>'outcome' = 'conforming' AND (violates_rule OR unresolved))
           OR (NEW.machine_box_result->>'outcome' = 'nonconforming' AND NOT violates_rule) THEN
            RAISE EXCEPTION 'Machine result disagrees with the applicable criteria or unresolved findings';
        END IF;
        IF (NEW.machine_box_result->>'denominator')::integer IS DISTINCT FROM
            (SELECT count(*) FROM observed_products o JOIN inspection_batches g ON g.id = o.batch_id
             WHERE g.inspection_id = NEW.id AND o.counted) THEN
            RAISE EXCEPTION 'Frozen denominator disagrees with the counted physical products';
        END IF;
    ELSIF NEW.state <> 'draft' THEN
        RAISE EXCEPTION 'A draft must be submitted before review';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER attempt_workflow BEFORE INSERT OR UPDATE ON inspections
FOR EACH ROW EXECUTE FUNCTION guard_attempt();

CREATE FUNCTION confirm_submission_event() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
BEGIN
    IF NOT EXISTS (SELECT FROM audit_logs a JOIN users u ON u.id = a.actor_id
        WHERE a.action = 'inspection_submitted' AND a.target_type = 'inspection' AND a.target_key = NEW.id::text
          AND u.active AND u.role = 'inspector' AND a.occurred_at = NEW.submitted_at
          AND a.details->>'transaction_id' = pg_current_xact_id()::text) THEN
        RAISE EXCEPTION 'Submission requires its authenticated, timestamped audit event';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER submission_event AFTER UPDATE ON inspections
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.state = 'submitted' AND OLD.state = 'draft')
EXECUTE FUNCTION confirm_submission_event();


-- Build the exact business payload checked again at insertion. The signer serializes it
-- to canonical UTF-8, signs those bytes externally, then inserts them unchanged.
CREATE FUNCTION decision_payload(p_lot bigint, p_signer bigint, p_version integer,
                                 p_outcome text, p_reason text) RETURNS jsonb
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE
    lot_row lots; profile inspection_profiles; rev jsonb; rules jsonb;
    choice record; slots jsonb := '[]'; hashes jsonb; defects integer := 0; suggestion text;
BEGIN
    SELECT * INTO STRICT lot_row FROM lots WHERE id = p_lot FOR UPDATE;
    IF lot_row.locked_at IS NULL OR NOT EXISTS
       (SELECT FROM users WHERE id = p_signer AND active AND can_review FOR SHARE) THEN
        RAISE EXCEPTION 'Finalization requires a locked plan and an active Reviewer';
    END IF;
    IF p_version <> 1 + coalesce((SELECT max(version) FROM lot_decisions WHERE lot_id = p_lot),0) THEN
        RAISE EXCEPTION 'Decision version must extend the lot history';
    END IF;
    rev := lot_row.plan_snapshot->'revisions'->-1;
    SELECT * INTO STRICT profile FROM inspection_profiles WHERE id = lot_row.profile_id;
    SELECT jsonb_agg(jsonb_build_object('code',code,'type',rule_type,'operator',operator,
        'limit_ratio',limit_ratio,'source_clause',source_clause) ORDER BY code COLLATE "C") INTO rules
    FROM quality_rules WHERE profile_id = profile.id;

    FOR choice IN
        SELECT s.slot_no, s.id AS selection_id, s.box_id, i.id AS attempt_id, i.state, i.inspector_id,
               i.machine_box_result, i.box_result, i.review_note, a.actor_id AS submitter,
               who.actor_id AS choice_reviewer, who.details->>'reason' AS choice_reason
        FROM current_selections s JOIN boxes b ON b.id = s.box_id
        LEFT JOIN LATERAL (SELECT actor_id, details FROM audit_logs
            WHERE action = 'attempt_selected' AND target_type = 'selection' AND target_key = s.id::text
            ORDER BY id DESC LIMIT 1) who ON true
        LEFT JOIN inspections i ON i.id = (who.details->>'inspection_id')::bigint AND i.selection_id = s.id
        LEFT JOIN audit_logs a ON a.action = 'inspection_submitted' AND a.target_type = 'inspection'
                              AND a.target_key = i.id::text
        WHERE b.lot_id = p_lot ORDER BY s.slot_no
    LOOP
        IF choice.state IS DISTINCT FROM 'reviewed' OR choice.submitter IS NULL
           OR p_signer IN (choice.inspector_id, choice.submitter)
           OR nullif(btrim(choice.choice_reason),'') IS NULL THEN
            RAISE EXCEPTION 'Every active slot needs an independent, reviewed, authoritative attempt';
        END IF;
        SELECT jsonb_agg(jsonb_build_object('image_id',im.id,'object_key',im.object_key,'sha256',im.sha256)
                         ORDER BY g.batch_no, im.id) INTO hashes
        FROM inspection_batches g JOIN inspection_images im ON im.batch_id = g.id
        WHERE g.inspection_id = choice.attempt_id;
        slots := slots || jsonb_build_array(jsonb_build_object('slot',choice.slot_no,'selection_id',choice.selection_id,
            'box_id',choice.box_id,'attempt_id',choice.attempt_id,'originals',hashes,
            'machine',choice.machine_box_result,'reviewed',choice.box_result,'review_note',choice.review_note,
            'choice_reviewer',choice.choice_reviewer,'choice_reason',choice.choice_reason));
        IF choice.box_result = 'nonconforming' THEN defects := defects + 1; END IF;
    END LOOP;
    IF jsonb_array_length(slots) <> (rev->>'n')::integer THEN
        RAISE EXCEPTION 'Active sample is incomplete';
    END IF;
    suggestion := CASE WHEN defects >= (rev->>'Re')::integer THEN 'reject' ELSE 'approve' END;
    RETURN jsonb_build_object('schema_version',1,'lot_id',p_lot,'decision_version',p_version,
        'plan_version',rev->'version','plan_sha256',encode(sha256(convert_to(rev::text,'UTF8')),'hex'),
        'criteria',jsonb_build_object('profile_id',profile.id,'version',profile.version,'reference',profile.reference,
                                      'applicability',profile.applicability,'rules',rules),
        'slots',slots,'d',defects,'Ac',rev->'Ac','Re',rev->'Re','recommendation',suggestion,
        'outcome',p_outcome,'reason',p_reason,'override_reason',CASE WHEN suggestion <> p_outcome THEN p_reason END,
        'signer_id',p_signer);
END $$;

CREATE FUNCTION check_decision() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE expected jsonb;
BEGIN
    expected := decision_payload(NEW.lot_id,NEW.reviewer_id,NEW.version,NEW.outcome,NEW.reason);
    IF convert_from(NEW.manifest_bytes,'UTF8')::jsonb IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'Signed payload differs from the authoritative lot facts';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_decision BEFORE INSERT ON lot_decisions
FOR EACH ROW EXECUTE FUNCTION check_decision();

CREATE FUNCTION check_decision_verification() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE fingerprint text := encode(sha256(NEW.certificate_der),'hex'); binding jsonb;
BEGIN
    SELECT a.details INTO binding FROM audit_logs a
    WHERE a.action = 'certificate_binding' AND a.target_type = 'user' AND a.target_key = NEW.reviewer_id::text
      AND a.details->>'fingerprint' = fingerprint AND a.occurred_at <= NEW.signed_at
    ORDER BY a.occurred_at DESC, a.id DESC LIMIT 1;
    IF binding->>'status' IS DISTINCT FROM 'active'
       OR NOT coalesce(NEW.signed_at BETWEEN (binding->>'valid_from')::timestamptz
                                         AND (binding->>'valid_until')::timestamptz,false)
       OR NOT EXISTS (SELECT FROM audit_logs a WHERE a.action = 'signature_verified'
           AND a.target_type = 'decision' AND a.target_key = NEW.id::text AND a.occurred_at >= NEW.signed_at
           AND nullif(a.details->>'verifier','') IS NOT NULL
           AND a.details->>'transaction_id' = pg_current_xact_id()::text
           AND a.details @> jsonb_build_object('success',true,'fingerprint',fingerprint,
               'manifest_sha256',encode(sha256(NEW.manifest_bytes),'hex'),
               'signature_sha256',encode(sha256(NEW.signature),'hex'),'algorithm','RSA-PSS/SHA-256')) THEN
        RAISE EXCEPTION 'Signed decision requires an enrolled certificate and matching successful verification';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER verified_decision AFTER INSERT ON lot_decisions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_decision_verification();

CREATE FUNCTION validate_audit_event() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
BEGIN
    IF NEW.action IN ('finding_corrected','signature_verified','inspection_submitted','replacement_authorized') THEN
        NEW.details := NEW.details || jsonb_build_object('transaction_id',pg_current_xact_id()::text);
    END IF;
    CASE NEW.action
    WHEN 'certificate_binding', 'order_imported' THEN
        IF NOT EXISTS (SELECT FROM users WHERE id = NEW.actor_id AND role = 'admin' AND active FOR SHARE) THEN
            RAISE EXCEPTION '% requires an active Admin', NEW.action;
        END IF;
        IF NEW.action = 'certificate_binding' AND (NEW.target_type <> 'user'
           OR NOT EXISTS (SELECT FROM users WHERE id::text = NEW.target_key AND can_review)
           OR NOT (NEW.details ?& ARRAY['fingerprint','valid_from','valid_until','status'])
           OR coalesce(NEW.details->>'fingerprint','') !~ '^[0-9a-f]{64}$'
           OR coalesce(NEW.details->>'status','') NOT IN ('active','revoked')) THEN
            RAISE EXCEPTION 'Invalid reviewer certificate binding';
        END IF;
    WHEN 'inspection_submitted' THEN
        IF NEW.target_type <> 'inspection' OR NOT EXISTS (SELECT FROM inspections i WHERE i.id::text=NEW.target_key
            AND i.state='submitted' AND i.submitted_at=NEW.occurred_at)
           OR NOT EXISTS (SELECT FROM users WHERE id=NEW.actor_id AND role='inspector' AND active FOR SHARE) THEN
            RAISE EXCEPTION 'Write the authenticated submission event immediately after submitting the draft';
        END IF;
    WHEN 'attempt_selected' THEN
        IF NEW.target_type <> 'selection' OR nullif(btrim(NEW.details->>'reason'),'') IS NULL
           OR NOT EXISTS (SELECT FROM inspections i JOIN current_selections s ON s.id = i.selection_id
               JOIN boxes b ON b.id = s.box_id JOIN lots l ON l.id = b.lot_id
               WHERE s.id::text = NEW.target_key AND i.id = (NEW.details->>'inspection_id')::bigint
               AND i.state = 'reviewed' FOR UPDATE OF l)
           OR NOT EXISTS (SELECT FROM users WHERE id = NEW.actor_id AND active AND can_review FOR SHARE) THEN
            RAISE EXCEPTION 'Authoritative choice requires a reviewed attempt, reason and authorized Reviewer';
        END IF;
    WHEN 'inference_result' THEN
        IF NEW.target_type <> 'image' OR NOT (NEW.details ?& ARRAY['inspection_id','execution_id','image_sha256',
            'stage','model_version','prompt_version','predicted_label','route','explanation_en','ocr',
            'schema_version','validation','error'])
           OR nullif(btrim(NEW.details->>'execution_id'),'') IS NULL
           OR NOT EXISTS (SELECT FROM inspection_images im JOIN inspection_batches g ON g.id = im.batch_id
               WHERE im.id::text = NEW.target_key AND im.sha256 = NEW.details->>'image_sha256'
                 AND g.inspection_id = (NEW.details->>'inspection_id')::bigint) THEN
            RAISE EXCEPTION 'Inference event must identify its immutable image, attempt, execution and provenance';
        END IF;
    ELSE NULL;
    END CASE;
    RETURN NEW;
END $$;
CREATE TRIGGER check_event BEFORE INSERT ON audit_logs
FOR EACH ROW EXECUTE FUNCTION validate_audit_event();


-- A locked revision and its complete selection are one unit of work.
CREATE FUNCTION confirm_sample_at_commit() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE expected integer; actual integer;
BEGIN
    SELECT (plan_snapshot->'revisions'->-1->>'n')::integer INTO expected FROM lots WHERE id = NEW.id;
    SELECT count(*) INTO actual FROM current_selections s JOIN boxes b ON b.id = s.box_id WHERE b.lot_id = NEW.id;
    IF actual IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'Commit all n active slots together with the sampling revision';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER complete_sample AFTER INSERT OR UPDATE ON lots
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.locked_at IS NOT NULL)
EXECUTE FUNCTION confirm_sample_at_commit();

CREATE FUNCTION validate_observation_findings() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE profile_key bigint; findings jsonb; expected_warning text;
BEGIN
    SELECT l.profile_id INTO STRICT profile_key FROM inspection_batches g JOIN inspections i ON i.id=g.inspection_id
    JOIN sample_selections s ON s.id=i.selection_id JOIN boxes b ON b.id=s.box_id JOIN lots l ON l.id=b.lot_id
    WHERE g.id=NEW.batch_id;
    FOREACH findings IN ARRAY ARRAY[NEW.ai_findings,NEW.review_findings] LOOP
        IF findings IS NULL THEN CONTINUE; END IF;
        IF EXISTS (SELECT FROM jsonb_array_elements(findings) e LEFT JOIN quality_rules q
            ON q.profile_id=profile_key AND q.code=e->>'code'
            WHERE q.id IS NULL OR coalesce(e->>'assessment','') NOT IN ('present','absent','uncertain')
               OR nullif(btrim(e->>'detail'),'') IS NULL)
           OR EXISTS (SELECT FROM jsonb_array_elements(findings) e GROUP BY e->>'code' HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'Findings require distinct applicable rule codes, assessments and supporting detail';
        END IF;
    END LOOP;
    expected_warning := CASE
        WHEN NEW.ai_findings @> '[{"assessment":"present"}]' THEN 'red'
        WHEN NEW.ai_findings @> '[{"assessment":"uncertain"}]'
            OR jsonb_array_length(NEW.ai_findings) <> (SELECT count(*) FROM quality_rules WHERE profile_id=profile_key)
            THEN 'yellow'
        ELSE 'green' END;
    IF NEW.warning <> expected_warning THEN RAISE EXCEPTION 'Warning disagrees with original findings'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_findings BEFORE INSERT OR UPDATE ON observed_products
FOR EACH ROW EXECUTE FUNCTION validate_observation_findings();

CREATE FUNCTION confirm_correction_event() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
DECLARE attempt_id bigint; physical_box bigint;
BEGIN
    SELECT i.id, s.box_id INTO STRICT attempt_id, physical_box FROM inspection_batches g
    JOIN inspections i ON i.id=g.inspection_id JOIN sample_selections s ON s.id=i.selection_id WHERE g.id=NEW.batch_id;
    IF NOT EXISTS (SELECT FROM audit_logs a JOIN users u ON u.id=a.actor_id
        WHERE a.action='finding_corrected' AND a.target_type='observation' AND a.target_key=NEW.id::text
          AND u.can_review AND u.active AND nullif(btrim(a.details->>'reason'),'') IS NOT NULL
          AND a.details @> jsonb_build_object('inspection_id',attempt_id,'before',OLD.review_findings,'after',NEW.review_findings)
          AND a.details->>'transaction_id' = pg_current_xact_id()::text
          AND NOT EXISTS (SELECT FROM inspections p JOIN sample_selections s ON s.id=p.selection_id
              LEFT JOIN audit_logs sub ON sub.action='inspection_submitted' AND sub.target_type='inspection'
                                       AND sub.target_key=p.id::text
              WHERE s.box_id=physical_box AND u.id IN (p.inspector_id,sub.actor_id))) THEN
        RAISE EXCEPTION 'Observation correction requires an independent Reviewer, timestamped reason and before/after audit';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER correction_event AFTER UPDATE ON observed_products
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (OLD.review_findings IS DISTINCT FROM NEW.review_findings)
EXECUTE FUNCTION confirm_correction_event();

-- Educational limits and lookup cells are only eligible for demonstration evidence.
CREATE FUNCTION guard_image_scope() RETURNS trigger
LANGUAGE plpgsql SET search_path = agroscan, pg_catalog AS $$
BEGIN
    IF NEW.usage_context='operational' AND EXISTS (
        SELECT FROM inspection_batches g JOIN inspections i ON i.id=g.inspection_id
        JOIN sample_selections s ON s.id=i.selection_id JOIN boxes b ON b.id=s.box_id JOIN lots l ON l.id=b.lot_id
        JOIN inspection_profiles p ON p.id=l.profile_id JOIN sampling_rules r ON r.id=l.sampling_rule_id
        WHERE g.id=NEW.batch_id AND (p.applicability->>'scope'='demo' OR r.verification->>'scope'='demo')) THEN
        RAISE EXCEPTION 'Operational evidence requires operational criteria and lookup';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER check_image_scope BEFORE INSERT ON inspection_images
FOR EACH ROW EXECUTE FUNCTION guard_image_scope();


COMMIT;
