-- ========================================================================================
-- Supabase Auth Schema & RLS Integration
-- ========================================================================================

-- Create admin_profiles table to link Supabase auth.users to our workspaces
CREATE TABLE IF NOT EXISTS public.admin_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    display_name TEXT,
    role TEXT DEFAULT 'admin', -- 'admin' or 'super_admin'
    status TEXT DEFAULT 'offline',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Set up RLS
ALTER TABLE public.admin_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can view their own profile"
    ON public.admin_profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Admins can update their own profile"
    ON public.admin_profiles FOR UPDATE
    USING (auth.uid() = id);

-- Trigger to keep updated_at current
CREATE OR REPLACE FUNCTION update_admin_profile_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trg_admin_profiles_updated_at
    BEFORE UPDATE ON public.admin_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_admin_profile_timestamp();

-- Function to handle new user signups
CREATE OR REPLACE FUNCTION public.handle_new_admin_signup()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.admin_profiles (id, display_name)
  VALUES (new.id, new.raw_user_meta_data->>'full_name');
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Expose trigger for new admin creation
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_admin_signup();

-- Example RLS addition to conversations table:
-- ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Admins see only their workspace conversations"
--   ON public.conversations FOR SELECT
--   USING (workspace_id IN (SELECT workspace_id FROM public.admin_profiles WHERE id = auth.uid()));
