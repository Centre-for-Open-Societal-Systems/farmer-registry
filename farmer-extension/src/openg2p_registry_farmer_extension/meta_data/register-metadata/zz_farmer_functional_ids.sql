-- Farmers entered through intake/staff approval need an ID just like imported
-- farmers. The base metadata disabled generation, leaving new records blank.
-- Keep this after the base seed, and make it safe to apply to existing sites.
UPDATE public.g2p_register_definitions
SET functional_id_generation_required = TRUE
WHERE register_id = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

-- Recover already-approved farmers through the normal allocation worker, not
-- by inventing IDs here. A stable recovery queue key and the existing-request
-- guard make repeated runs safe, including while an allocation is pending.
INSERT INTO public.g2p_functional_id_generation_queue (
    queue_id, register_id, internal_record_id,
    id_allocation_status, id_allocation_no_of_attempts,
    id_updation_status, id_updation_no_of_attempts
)
SELECT
    'farmer-id-recovery-' || farmer.internal_record_id,
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', farmer.internal_record_id,
    'PENDING', 0, 'NOT_APPLICABLE', 0
FROM public.g2p_register_farmers AS farmer
WHERE NULLIF(btrim(farmer.functional_record_id), '') IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM public.g2p_functional_id_generation_queue AS queue
      WHERE queue.register_id = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
        AND queue.internal_record_id = farmer.internal_record_id
  )
ON CONFLICT (queue_id) DO NOTHING;
