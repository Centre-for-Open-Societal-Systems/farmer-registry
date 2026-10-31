-- Additive compatibility for existing COSS databases, through OAN's native
-- extension migration hook. Existing values, identifiers and checkpoints stay.
DO $native_compat$
DECLARE prefix text;
BEGIN
  IF to_regclass('public.outgoing_topics') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outgoing_topics' AND column_name='topic_type') THEN
      -- Legacy topics were register-scoped. Refuse ambiguous source rows rather
      -- than inventing a partner-topic classification.
      IF EXISTS (SELECT 1 FROM public.outgoing_topics WHERE register_id IS NULL) THEN
        RAISE EXCEPTION 'Legacy outgoing topics require an explicit register/partner migration';
      END IF;
      -- A column default fills old tuples without firing row-update triggers.
      ALTER TABLE public.outgoing_topics ADD COLUMN IF NOT EXISTS topic_type varchar NOT NULL DEFAULT 'REGISTER';
      ALTER TABLE public.outgoing_topics ALTER COLUMN topic_type DROP DEFAULT;
    END IF;
    ALTER TABLE public.outgoing_topics ADD COLUMN IF NOT EXISTS partner_id varchar;
  END IF;
  FOREACH prefix IN ARRAY ARRAY['g2p_register_', 'g2p_register_history_', 'g2p_intake_form_'] LOOP
    IF to_regclass('public.' || prefix || 'households') IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS number_of_elderly_members integer', prefix || 'households');
    END IF;
    IF to_regclass('public.' || prefix || 'household_members') IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS is_head boolean', prefix || 'household_members');
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS relationship_to_the_head varchar', prefix || 'household_members');
    END IF;
  END LOOP;
END;
$native_compat$;
