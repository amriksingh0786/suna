-- Migration to support x-api user account creation
-- This function creates a personal account for x-api users who don't have one

CREATE OR REPLACE FUNCTION public.ensure_x_api_user_account(x_api_user_id uuid)
    RETURNS uuid
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public, basejump
AS $$
DECLARE
    account_id uuid;
    user_exists boolean;
BEGIN
    -- Check if the user already has an account
    SELECT id INTO account_id
    FROM basejump.accounts
    WHERE id = x_api_user_id;
    
    -- If account exists, return it
    IF account_id IS NOT NULL THEN
        RETURN account_id;
    END IF;
    
    -- Check if user exists in auth.users
    SELECT EXISTS(SELECT 1 FROM auth.users WHERE id = x_api_user_id) INTO user_exists;
    
    -- If user doesn't exist in auth.users, create them
    IF NOT user_exists THEN
        INSERT INTO auth.users (
            id,
            email,
            email_confirmed_at,
            created_at,
            updated_at,
            raw_app_meta_data,
            raw_user_meta_data,
            is_super_admin,
            role
        ) VALUES (
            x_api_user_id,
            'x-api-user-' || x_api_user_id || '@placeholder.com',
            now(),
            now(),
            now(),
            '{"provider": "x-api", "providers": ["x-api"]}',
            '{"source": "x-api"}',
            false,
            'authenticated'
        );
    END IF;
    
    -- Create a personal account for the x-api user
    INSERT INTO basejump.accounts (
        id,
        primary_owner_user_id,
        name,
        personal_account,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (
        x_api_user_id,
        x_api_user_id,
        'Personal Account',
        true,
        now(),
        now(),
        x_api_user_id,
        x_api_user_id
    )
    RETURNING id INTO account_id;
    
    -- Add the user to the account_user table
    INSERT INTO basejump.account_user (
        user_id,
        account_id,
        account_role
    ) VALUES (
        x_api_user_id,
        account_id,
        'owner'
    );
    
    RETURN account_id;
END;
$$;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION public.ensure_x_api_user_account(uuid) TO authenticated, service_role; 