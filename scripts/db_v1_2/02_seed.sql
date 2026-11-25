-- Five synthetic lots and one offline-signed, demonstration-only decision.
-- Stable negative fixture IDs keep manifests portable without advancing production identities.
-- Exact original 96 x 64 RGB PNG used by all demo image references (base64):
-- iVBORw0KGgoAAAANSUhEUgAAAGAAAABACAIAAABqVuVZAAAAxElEQVR4nO3boQ0CQRBA0T2Cpjgkigqw1IClAhSSus6REAqggrufEHDv2dkxP2N3er7nwbLNygyBmgsKAgWBgkBBoCBQECgIFAQK26XB+X4av3Y5XL9bfD2O4w92+1u+cUFBoCBQECgIFAQKAgWBgkBBoCBQECgIFAQKAgWBgkBBoCBQECgIFAQKAgWBgkBBoCBQECgIFAQKAgWBwuQzyzoXFAQKAgWBgkBBoCBQECgIFAQKAgWBgkBBoCBQECgIFAQa6z6ofwwXSzGmLQAAAABJRU5ErkJggg==
-- The SQL loads metadata only. A real MinIO object is never implied by an INSERT.
BEGIN;
SET LOCAL search_path TO agroscan, pg_catalog;
-- Do not fall back to another schema if the v1.2 installation is missing.
LOCK TABLE agroscan.audit_logs IN SHARE ROW EXCLUSIVE MODE;

DO $seed$
DECLARE
    codes text[] := ARRAY['apple','orange','banana','shrimp','squid'];
    names text[] := ARRAY['Apple','Orange','Banana','Shrimp','Squid'];
    product_pk bigint; profile_pk bigint; lot_pk bigint; box_pk bigint; selection_pk bigint;
    attempt_pk bigint; prior_pk bigint; batch_pk bigint; image_pk bigint;
    admin_pk constant bigint := -120001; maker constant bigint := -120002;
    second_maker constant bigint := -120003; reviewer constant bigint := -120004;
    rule_pk constant bigint := -120001;
    base_time constant timestamptz := '2026-11-24 01:00:00+00';
    original_hash constant text := 'd10ea8cc51b40a02488dadc49a08a57967f742b557af079c7a4cc0a4c98a8e37';
    rev jsonb; selected_ids jsonb; findings jsonb; class_counts jsonb; batches jsonb;
    scenario integer; box_no integer; slot integer; attempt integer; group_no integer; unit integer;
    num_slots integer; attempts integer; groups integer; is_defect boolean; needs_retake boolean;
    when_started timestamptz; submitted timestamptz; resolution text; defect_units integer;
BEGIN
    IF EXISTS (SELECT FROM audit_logs WHERE action = 'fixture_loaded' AND target_type = 'fixture'
               AND target_key = 'agroscan-v1.2-five-lots') THEN RETURN; END IF;

    -- These accounts identify actors in historical examples. Their "!" hashes disable password login.
    INSERT INTO users(id,login,password_hash,role,can_review) OVERRIDING SYSTEM VALUE VALUES
        (admin_pk,'demo12.admin','!','admin',false),
        (maker,'demo12.inspector.a','!','inspector',false),
        (second_maker,'demo12.inspector.b','!','inspector',false),
        (reviewer,'demo12.reviewer','!','inspector',true),
        (-120005,'demo12.manager','!','manager',false);
    INSERT INTO sampling_rules(id,edition,level_code,aql,n_min,n_max,sample_n,ac,re,verification)
    OVERRIDING SYSTEM VALUE VALUES (rule_pk,'DEMO-LOOKUP-v1','DEMO',2.5,3,4,2,0,1,
        '{"scope":"demo","status":"verified","source":"Synthetic training fixture; not TCVN","cell":"D1"}');

    FOR scenario IN 1..5 LOOP
        profile_pk := -120000 - scenario;
        lot_pk := -120000 - scenario;
        INSERT INTO products(code,name,category)
        VALUES (codes[scenario],names[scenario],CASE WHEN scenario <= 3 THEN 'agricultural' ELSE 'aquatic' END)
        ON CONFLICT (code) DO NOTHING;
        SELECT id INTO STRICT product_pk FROM products WHERE code = codes[scenario];
        INSERT INTO inspection_profiles(id,product_id,version,reference,applicability)
        OVERRIDING SYSTEM VALUE VALUES (profile_pk,product_pk,120001,'DEMO profile / ' || codes[scenario],
            jsonb_build_object('scope','demo','form','whole','species_or_variety',names[scenario],
                               'grade','training','source_edition','DEMO-QUALITY-v1'));
        INSERT INTO quality_rules(profile_id,code,rule_type,operator,limit_ratio,source_clause) VALUES
            (profile_pk,'visible_damage','ratio','gt',0.25,'DEMO-Q1'),
            (profile_pk,'foreign_material','exclusion',NULL,NULL,'DEMO-Q2');
        UPDATE inspection_profiles SET approved = true WHERE id = profile_pk;
        INSERT INTO orders(id,order_code,supplier,customer,source_file,imported_at) OVERRIDING SYSTEM VALUE
        VALUES (lot_pk,format('DEMO-V12-0%s',scenario),'Demo Supplier ' || scenario,'Demo Buyer',
                format('demo/import/order-0%s.csv',scenario),base_time);
        INSERT INTO lots(id,order_id,profile_id,lot_code,declared_boxes,container_ref) OVERRIDING SYSTEM VALUE
        VALUES (lot_pk,lot_pk,profile_pk,'LOT-01',3,'DEMO-C' || scenario);
        FOR box_no IN 1..3 LOOP
            box_pk := -120000 - scenario*10 - box_no;
            INSERT INTO boxes(id,lot_id,box_code,scan_token) OVERRIDING SYSTEM VALUE
            VALUES (box_pk,lot_pk,'BOX-0' || box_no,
                   ('00000000-0000-4000-8000-' || lpad(abs(box_pk)::text,12,'0'))::uuid);
        END LOOP;
        INSERT INTO audit_logs(actor_id,action,target_type,target_key,details,occurred_at)
        VALUES (admin_pk,'order_imported','order',lot_pk::text,jsonb_build_object('lot_id',lot_pk,
            'declared_boxes',3,'declared_weight',60,'weight_unit','kg','scope','demo'),base_time);
        IF scenario = 1 THEN CONTINUE; END IF;

        selected_ids := jsonb_build_array(-120000-scenario*10-1,-120000-scenario*10-2);
        rev := jsonb_build_object('version',1,'N',3,'level','DEMO','aql',2.5,'lookup_table','DEMO-LOOKUP-v1',
            'lookup_cell',rule_pk,'n',2,'Ac',0,'Re',1,'register_sha256',register_digest(lot_pk),
            'seed','fixture-0' || scenario,'algorithm_version','fixture-list-v1','selected_box_ids',selected_ids);
        UPDATE lots SET sampling_rule_id = rule_pk, locked_at = base_time + interval '2 minutes',
            plan_snapshot = jsonb_build_object('active_version',1,'revisions',jsonb_build_array(rev))
        WHERE id = lot_pk;
        FOR slot IN 1..2 LOOP
            INSERT INTO sample_selections(id,box_id,slot_no,plan_version,selected_at) OVERRIDING SYSTEM VALUE
            VALUES (-120000-scenario*100-slot,-120000-scenario*10-slot,slot,1,base_time + interval '2 minutes');
        END LOOP;
        IF scenario = 2 THEN
            -- Register correction before inspection: preserve v1 and switch to the full v2 sample.
            box_pk := -120024;
            INSERT INTO boxes(id,lot_id,box_code,scan_token) OVERRIDING SYSTEM VALUE
            VALUES (box_pk,lot_pk,'BOX-04','00000000-0000-4000-8000-000000120024');
            selected_ids := jsonb_build_array(-120023,-120022);
            rev := rev || jsonb_build_object('version',2,'prior_version',1,'reason','Fourth box confirmed at intake',
                'open_attempt_disposition','No attempts had started','N',4,'selected_box_ids',selected_ids,
                'seed','fixture-02-r2','register_sha256',register_digest(lot_pk));
            UPDATE lots SET declared_boxes = 4, plan_snapshot = jsonb_build_object('active_version',2,
                'revisions',(plan_snapshot->'revisions') || jsonb_build_array(rev)) WHERE id = lot_pk;
            INSERT INTO sample_selections(id,box_id,slot_no,plan_version,selected_at) OVERRIDING SYSTEM VALUE VALUES
                (-120211,-120023,1,2,base_time + interval '3 minutes'),
                (-120212,-120022,2,2,base_time + interval '3 minutes');
            INSERT INTO sample_selections(id,box_id,slot_no,plan_version,replaces_id,reason,selected_at)
            OVERRIDING SYSTEM VALUE VALUES (-120213,-120024,1,2,-120211,'Seal inaccessible before inspection',
                                            base_time + interval '4 minutes');
            INSERT INTO audit_logs(actor_id,action,target_type,target_key,details,occurred_at)
            VALUES (reviewer,'replacement_authorized','selection','-120213',
                '{"replaces_id":-120211,"reason":"Seal inaccessible before inspection"}',base_time + interval '4 minutes');
            CONTINUE;
        END IF;

        num_slots := CASE WHEN scenario = 5 THEN 2 ELSE 1 END;
        FOR slot IN 1..num_slots LOOP
            selection_pk := -120000-scenario*100-slot;
            attempts := CASE WHEN scenario = 5 AND slot = 1 THEN 2 ELSE 1 END;
            prior_pk := NULL;
            FOR attempt IN 1..attempts LOOP
                attempt_pk := -120000-scenario*100-slot*10-attempt;
                needs_retake := scenario = 5 AND slot = 1 AND attempt = 1;
                groups := CASE WHEN scenario = 4 THEN 2 ELSE 1 END;
                when_started := base_time + (scenario*10 + slot*4 + attempt*2) * interval '1 minute';
                submitted := when_started + interval '30 seconds';
                INSERT INTO inspections(id,selection_id,previous_id,inspector_id,attempt_no,station_code,ai_versions,checkpoint)
                OVERRIDING SYSTEM VALUE VALUES (attempt_pk,selection_pk,prior_pk,
                    CASE WHEN attempt = 2 THEN second_maker ELSE maker END,attempt,'DEMO-STATION-01',
                    '{"detector":"fixture-cv-1","prompt":"fixture-p1","evaluation":"fixture-rule-1"}',
                    jsonb_build_object('phase','capturing','operation_id','capture-' || attempt_pk,
                                       'last_successful_stage','intake','evidence_refs','[]'::jsonb,'error',NULL));
                prior_pk := attempt_pk;
                batches := '[]'; defect_units := 0;
                FOR group_no IN 1..groups LOOP
                    batch_pk := attempt_pk*10-group_no;
                    image_pk := batch_pk*10-1;
                    INSERT INTO inspection_batches(id,inspection_id,batch_no,coverage_note) OVERRIDING SYSTEM VALUE
                    VALUES (batch_pk,attempt_pk,group_no,'Distinct physical group ' || group_no);
                    batches := batches || jsonb_build_array(batch_pk);
                    INSERT INTO inspection_images(id,batch_id,is_count_image,object_key,sha256,width_px,height_px,
                                                  source_kind,usage_context,captured_at,received_at)
                    OVERRIDING SYSTEM VALUE VALUES (image_pk,batch_pk,true,format('demo/v12/%s/count.png',batch_pk),
                        original_hash,96,64,'imported_image','demo',NULL,when_started);
                    IF scenario = 4 AND group_no = 1 THEN
                        INSERT INTO inspection_images(batch_id,is_count_image,object_key,sha256,width_px,height_px,
                            source_kind,usage_context,captured_at,received_at)
                        VALUES (batch_pk,false,'demo/v12/shrimp/side.png',original_hash,96,64,'camera','demo',when_started,when_started);
                    END IF;
                    INSERT INTO audit_logs(action,target_type,target_key,details,occurred_at)
                    VALUES ('inference_result','image',image_pk::text,jsonb_build_object('inspection_id',attempt_pk,
                        'execution_id','run-' || image_pk,'image_sha256',original_hash,'stage','detector',
                        'model_version','fixture-cv-1','prompt_version','fixture-p1','predicted_label','demo_objects',
                        'confidence',0.91,'route','local_fixture','explanation_en','Two synthetic objects in the count image.',
                        'ocr',jsonb_build_object('readability','not_applicable'),'schema_version','1','validation','valid','error',NULL),
                        when_started + interval '1 second');
                    FOR unit IN 1..2 LOOP
                        is_defect := scenario = 5 AND slot = 2 AND unit = 2;
                        IF is_defect THEN defect_units := defect_units + 1; END IF;
                        findings := jsonb_build_array(jsonb_build_object('code','visible_damage','assessment',
                            CASE WHEN is_defect THEN 'present' WHEN needs_retake THEN 'uncertain' ELSE 'absent' END,
                            'detail','Synthetic surface assessment'),jsonb_build_object('code','foreign_material',
                            'assessment','absent','detail','No foreign material observed'));
                        INSERT INTO observed_products(batch_id,count_image_id,unit_no,x,y,width,height,ai_findings,warning)
                        VALUES (batch_pk,image_pk,unit,CASE WHEN unit=1 THEN 8 ELSE 55 END,12,27,32,findings,
                            CASE WHEN is_defect THEN 'red' WHEN needs_retake THEN 'yellow' ELSE 'green' END);
                    END LOOP;
                END LOOP;
                IF scenario = 3 THEN CONTINUE; END IF;
                resolution := CASE WHEN needs_retake THEN 'needs_review' WHEN defect_units > 0 THEN 'nonconforming' ELSE 'conforming' END;
                class_counts := jsonb_build_object('clear',CASE WHEN needs_retake THEN 0 ELSE 2*groups-defect_units END,
                    'damaged',defect_units,'uncertain',CASE WHEN needs_retake THEN 2*groups ELSE 0 END);
                UPDATE inspections SET state = 'submitted', submitted_at = submitted,
                    checkpoint = jsonb_build_object('phase','submitted','operation_id','submit-' || attempt_pk,
                        'last_successful_stage','rule_evaluation','evidence_refs',batches,'error',NULL),
                    coverage = jsonb_build_object('confirmed',true,'inspector_id',inspector_id,'confirmed_at',submitted,'batch_ids',batches),
                    machine_box_result = jsonb_build_object('class_counts',class_counts,'denominator',2*groups,
                        'comparisons',jsonb_build_array(jsonb_build_object('code','visible_damage','affected',defect_units,
                            'operator','gt','limit_ratio',0.25,'ratio',round(defect_units::numeric/(2*groups),2))),
                        'exclusions',jsonb_build_array(jsonb_build_object('code','foreign_material','present',false)),'outcome',resolution)
                WHERE id = attempt_pk;
                INSERT INTO audit_logs(actor_id,action,target_type,target_key,details,occurred_at)
                SELECT inspector_id,'inspection_submitted','inspection',id::text,'{"scope":"demo"}',submitted
                FROM inspections WHERE id = attempt_pk;
                IF scenario = 4 THEN CONTINUE; END IF;
                UPDATE inspections SET state = CASE WHEN needs_retake THEN 'reinspect' ELSE 'reviewed' END,
                    reviewer_id = reviewer, reviewed_at = submitted + interval '30 seconds',
                    box_result = CASE WHEN NOT needs_retake THEN resolution END,
                    review_note = CASE WHEN needs_retake THEN 'Repeat whole-box capture due to uncertain surface evidence.'
                        WHEN defect_units > 0 THEN 'One damaged unit out of two exceeds the demo limit.'
                        ELSE 'Whole-box evidence reviewed and cleared.' END
                WHERE id = attempt_pk;
                IF NOT needs_retake THEN
                    INSERT INTO audit_logs(actor_id,action,target_type,target_key,details,occurred_at)
                    VALUES (reviewer,'attempt_selected','selection',selection_pk::text,
                        jsonb_build_object('inspection_id',attempt_pk,'reason','Latest complete independently reviewed attempt'),
                        submitted + interval '31 seconds');
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;
END $seed$;

-- Archived demonstration fixture: independently verified exact bytes (RSA-PSS,
-- MGF1-SHA256, salt length 32). Verification below rechecks their pinned digests.
DO $signed_fixture$
DECLARE
    signer constant bigint := -120004;
    admin_user constant bigint := -120001;
    signed_time constant timestamptz := '2026-11-24 03:00:00+00';
    cert bytea := decode('MIIDTjCCAjagAwIBAgIUFDLMIX134rAMTO0qKgSMmEGTCC0wDQYJKoZIhvcNAQELBQAwUDEfMB0GA1UECgwWQWdyb1NjYW4gQ2Fwc3RvbmUgRGVtbzEtMCsGA1UEAwwkZGVtbzEyLnJldmlld2VyIC0gZGVtb25zdHJhdGlvbiBvbmx5MB4XDTI2MTEwMTAwMDAwMFoXDTI3MTEwMTAwMDAwMFowUDEfMB0GA1UECgwWQWdyb1NjYW4gQ2Fwc3RvbmUgRGVtbzEtMCsGA1UEAwwkZGVtbzEyLnJldmlld2VyIC0gZGVtb25zdHJhdGlvbiBvbmx5MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAimBBl81Tz4P6JoY8RkXvFsjI34lM69glnLF/uYrtIv+t7onBj0u1Z/rIr56yqGuIba5Yb1WIvbrXw0DijUMQ7W8NF7KoAdXAlqB1CTuvVpBH10bXEdDfjWovRJt38HLjo/TZlpoZLxunSikcvaMSqH8gqSTdTdrxMMeZx2OL2w/0WnoWUzNYp7m6CqWJn+G6RyxVZvUFfpiIwQ9sCURpiKFdVmQmSqoVKzaCiKLFslw7isqQo1KD4jciLzjMrk/lu2DRpWrw3FDDrK5wjaK1alpMEx5qMHLLNghyBG7tGGQN5RDJX5ZRADHfe4ZUKs6ROuvMyjYgPKMTQNNKXH2a9wIDAQABoyAwHjAMBgNVHRMBAf8EAjAAMA4GA1UdDwEB/wQEAwIGwDANBgkqhkiG9w0BAQsFAAOCAQEAZofdc1jFKvGZQowlpOqxnYEyd8cZE0T1yooP7AE45+XBe5HA1IZJDz5wAGH8bsg1DksUROVgakPNQBO6Xmm8lmrN5CHW9VXWaQnYEqKWFXmgslCFLWV8JEYMi0x4muPAzjz0nmOUBbD8gmKaUzSNazUdHe5qVX2RFx76tWSAURiDjyHPyzSsWMfAuzQ5x3G7EWmdv9Q8Af7TGUzMlzGE3DFbEfTfxzyOTFKyJwIrswHCJkTS1GToGVh7kUCJyYNGY6W8xOXbrzz1B5YEB8xeqhc3qMzKgJNp8KNP8+sw0UiDSeZKJ7kSnQESId+9CqTdNIlyEAEhkH1teyr/vrqLrQ==','base64');
    sig bytea := decode('CjkEuz6Uy/80AwTAJwPH0QuI12agbUlstl/rK34UHaV6dfN/hrqw0TXw4MvvnfUInL6YtThvOKLB87iAmBF4/S8lazgSNoNuIg07jjbU8+zvsvVZjA6cREjQanzfCmBM44v23dQaKxDLecuhRXl9tFC2gAG4Xj49nr+9e867qvUGFvSOKPbadl1wyvZRnr0/AbSsrbYVQoaB/gVKliJWkuqjdlWRjQY9rKiXgByat0WeHj2HAePi5CgLESCtrX6KU6fh6xUXyLXuZOaOdeh9eU80MyUpFJF/KQplSuXqEwfTusUIqARbaHDNPjvApYZ+PeqpAqUy3SZmwqz5CRwkDg==','base64');
    payload bytea := convert_to($manifest${"Ac":0,"Re":1,"criteria":{"applicability":{"form":"whole","grade":"training","scope":"demo","source_edition":"DEMO-QUALITY-v1","species_or_variety":"Squid"},"profile_id":-120005,"reference":"DEMO profile / squid","rules":[{"code":"foreign_material","limit_ratio":null,"operator":null,"source_clause":"DEMO-Q2","type":"exclusion"},{"code":"visible_damage","limit_ratio":0.25,"operator":"gt","source_clause":"DEMO-Q1","type":"ratio"}],"version":120001},"d":1,"decision_version":1,"lot_id":-120005,"outcome":"approve","override_reason":"Demo buyer accepts the documented surface damage by exception.","plan_sha256":"8432812e255ed20ec2c36a409ae92093d6c92625e88a9cd267d3280426933147","plan_version":1,"reason":"Demo buyer accepts the documented surface damage by exception.","recommendation":"reject","schema_version":1,"signer_id":-120004,"slots":[{"attempt_id":-120512,"box_id":-120051,"choice_reason":"Latest complete independently reviewed attempt","choice_reviewer":-120004,"machine":{"class_counts":{"clear":2,"damaged":0,"uncertain":0},"comparisons":[{"affected":0,"code":"visible_damage","limit_ratio":0.25,"operator":"gt","ratio":0.0}],"denominator":2,"exclusions":[{"code":"foreign_material","present":false}],"outcome":"conforming"},"originals":[{"image_id":-12051211,"object_key":"demo/v12/-1205121/count.png","sha256":"d10ea8cc51b40a02488dadc49a08a57967f742b557af079c7a4cc0a4c98a8e37"}],"review_note":"Whole-box evidence reviewed and cleared.","reviewed":"conforming","selection_id":-120501,"slot":1},{"attempt_id":-120521,"box_id":-120052,"choice_reason":"Latest complete independently reviewed attempt","choice_reviewer":-120004,"machine":{"class_counts":{"clear":1,"damaged":1,"uncertain":0},"comparisons":[{"affected":1,"code":"visible_damage","limit_ratio":0.25,"operator":"gt","ratio":0.5}],"denominator":2,"exclusions":[{"code":"foreign_material","present":false}],"outcome":"nonconforming"},"originals":[{"image_id":-12052111,"object_key":"demo/v12/-1205211/count.png","sha256":"d10ea8cc51b40a02488dadc49a08a57967f742b557af079c7a4cc0a4c98a8e37"}],"review_note":"One damaged unit out of two exceeds the demo limit.","reviewed":"nonconforming","selection_id":-120502,"slot":2}]}$manifest$,'UTF8');
    decision_id bigint;
BEGIN
    IF EXISTS (SELECT FROM audit_logs WHERE action='fixture_loaded' AND target_type='fixture'
               AND target_key='agroscan-v1.2-five-lots') THEN RETURN; END IF;
    IF encode(sha256(cert),'hex') <> '71217554eb957c5f9b195e75a0bf6498cb26743879d4debaf43a7bde91770b2a'
       OR encode(sha256(sig),'hex') <> '6e77bd4b408abb5eaae79741d504d20566e6cad793587e0e35a9b5b9cdac6e76'
       OR encode(sha256(payload),'hex') <> '97d305f8d6ae80cdc5f765807c58773dbab4c9d0ddc51315bd6f400cdc907562' THEN
        RAISE EXCEPTION 'Demo fixture bytes have changed; independent verification is required';
    END IF;
    INSERT INTO audit_logs(actor_id,action,target_type,target_key,details,occurred_at)
    VALUES (admin_user,'certificate_binding','user',signer::text,
        jsonb_build_object('fingerprint','71217554eb957c5f9b195e75a0bf6498cb26743879d4debaf43a7bde91770b2a','status','active','valid_from','2026-11-01T00:00:00Z',
            'valid_until','2027-11-01T00:00:00Z','usage','demonstration only'),signed_time - interval '1 day');
    INSERT INTO lot_decisions(lot_id,reviewer_id,version,outcome,reason,manifest_bytes,signature,certificate_der,signed_at)
    VALUES (-120005,signer,1,'approve','Demo buyer accepts the documented surface damage by exception.',
            payload,sig,cert,signed_time) RETURNING id INTO decision_id;
    INSERT INTO audit_logs(action,target_type,target_key,details,occurred_at)
    VALUES ('signature_verified','decision',decision_id::text,
        jsonb_build_object('verifier','Offline fixture verifier / Python cryptography','success',true,
            'algorithm','RSA-PSS/SHA-256','fingerprint','71217554eb957c5f9b195e75a0bf6498cb26743879d4debaf43a7bde91770b2a','manifest_sha256','97d305f8d6ae80cdc5f765807c58773dbab4c9d0ddc51315bd6f400cdc907562',
            'signature_sha256','6e77bd4b408abb5eaae79741d504d20566e6cad793587e0e35a9b5b9cdac6e76','scope','demo'),signed_time);
    INSERT INTO audit_logs(actor_id,action,target_type,target_key,details,occurred_at)
    VALUES (admin_user,'fixture_loaded','fixture','agroscan-v1.2-five-lots','{"lots":5,"scope":"demo"}',signed_time);
END $signed_fixture$;

COMMIT;
