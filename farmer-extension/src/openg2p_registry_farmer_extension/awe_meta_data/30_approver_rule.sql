-- OpenG2P native default stages under clean keys; old policies/tasks remain intact.
-- Every stage lists the named officer and admin; one decision from either completes it.
INSERT INTO public.approver_rule (id,stage_id,rule_type,rule_value,kind,required,created_at,updated_at)
SELECT v.id,s.id,'user',v.rule_value::json,'approver',FALSE,NOW(),NOW()
FROM (VALUES
('18996095-e906-53ef-9cb3-a416220063ae','registry.change_request.farmer.default',1,'{"user_id": "alex.carter"}'),
('3e76f6e1-ffca-5a06-897b-3054b93aaeaa','registry.change_request.farmer.default',1,'{"user_id": "admin"}'),
('5660c583-6ff9-521c-ae12-d072437ff444','registry.change_request.farmer.default',2,'{"user_id": "nina.patel"}'),
('a79934ee-3182-5702-a238-1ed6befe02e7','registry.change_request.farmer.default',2,'{"user_id": "admin"}'),
('01f818a7-1961-518e-8f15-dc28ea356180','registry.change_request.household.default',1,'{"user_id": "alex.carter"}'),
('626e38da-f00d-5397-a5a9-b98d55f962cd','registry.change_request.household.default',1,'{"user_id": "admin"}'),
('863f9a7a-5e7f-51f8-b460-04137b0975b5','registry.change_request.household.default',2,'{"user_id": "nina.patel"}'),
('e6ec34e3-39b4-57df-999f-eaa9c0b98209','registry.change_request.household.default',2,'{"user_id": "admin"}'),
('30fa0b18-e46e-5ab3-a574-987be893275d','registry.intake_form.farmer.default',1,'{"user_id": "alex.carter"}'),
('117f8939-2654-5136-83cf-63ed70da415c','registry.intake_form.farmer.default',1,'{"user_id": "admin"}'),
('a9621de2-b393-5a97-a114-2ac64143fb17','registry.intake_form.farmer.default',2,'{"user_id": "nina.patel"}'),
('099a19ca-e2f6-5054-9ad1-4da0de9552c5','registry.intake_form.farmer.default',2,'{"user_id": "admin"}'),
('e3b06e13-591b-5ff7-8e66-e6bc946732f2','registry.intake_form.household.default',1,'{"user_id": "alex.carter"}'),
('d67b238a-7912-57eb-9763-9a5de4e47d5a','registry.intake_form.household.default',1,'{"user_id": "admin"}'),
('f8d6485f-48c7-5bf7-9f64-61cb8a847a51','registry.intake_form.household.default',2,'{"user_id": "nina.patel"}'),
('deaf357e-66a6-54a1-bf50-f93c040bea65','registry.intake_form.household.default',2,'{"user_id": "admin"}')) AS v(id,policy_key,stage_order,rule_value)
JOIN public.approval_policy p ON p.policy_key=v.policy_key AND p.version=1
JOIN public.approval_stage s ON s.policy_id=p.id AND s.stage_order=v.stage_order
WHERE NOT EXISTS (SELECT 1 FROM public.approver_rule r WHERE r.stage_id=s.id AND r.rule_type='user' AND r.rule_value::text=v.rule_value)
ON CONFLICT (id) DO NOTHING;
