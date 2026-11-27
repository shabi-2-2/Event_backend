import { Settings2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ConfigurationRequired() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-12">
      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle>Frontend configuration required</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert variant="warning">
            <Settings2 className="h-4 w-4" aria-hidden="true" />
            <AlertTitle className="font-medium">Missing public environment values</AlertTitle>
            <AlertDescription className="mt-1 text-sm text-muted-foreground">
              Copy <code>frontend/.env.example</code> to <code>frontend/.env.local</code> and
              provide the Supabase project URL and publishable key, then restart the dev server.
            </AlertDescription>
          </Alert>
          <p className="text-xs text-muted-foreground">
            Never add a service-role key, database URL, or backend secret to frontend configuration.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
