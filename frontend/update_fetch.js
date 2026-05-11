const fs = require('fs');
const glob = require('glob');
const path = require('path');

const files = glob.sync('app/**/page.tsx', { cwd: __dirname, absolute: true });

files.forEach(filePath => {
    let content = fs.readFileSync(filePath, 'utf-8');

    if (content.includes('fetchJson')) {
        let modified = false;

        // Add createClient import
        if (!content.includes('createClient')) {
            content = content.replace(
                /import (\{[^}]+\}) from "@\/lib\/runtime-config"/,
                (match, p1) => `import ${p1} from "@/lib/runtime-config"\nimport { createClient } from "@/lib/supabase/server"`
            );
            modified = true;
        }

        // Add session logic
        if (content.includes('const config = getFrontendRuntimeConfig()') && !content.includes('const supabase = await createClient()')) {
            content = content.replace(
                'const config = getFrontendRuntimeConfig()',
                `const config = getFrontendRuntimeConfig()\n  const supabase = await createClient()\n  const { data: { session } } = await supabase.auth.getSession()\n  const tenantId = session?.user?.id\n  const accessToken = session?.access_token\n`
            );
            modified = true;
        }

        // Replace fetchJson calls to include tenantId and accessToken
        const regex = /fetchJson<([^>]+)>\(([^,]+)(?:,\s*({[^}]+}))?\)/g;
        if (content.match(regex)) {
             content = content.replace(regex, (match, type, arg1, optionsObj) => {
                 let inner = optionsObj ? optionsObj.slice(1, -1).trim() + ',' : '';
                 return `fetchJson<${type}>(${arg1}, { ${inner} tenantId, accessToken })`;
             });
             modified = true;
        }

        if (modified) {
            fs.writeFileSync(filePath, content, 'utf-8');
            console.log(`Updated ${filePath}`);
        }
    }
});
