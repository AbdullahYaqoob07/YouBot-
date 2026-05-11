"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { createClient } from "@/lib/supabase/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2 } from "lucide-react"

export default function SignupPage() {
  const router = useRouter()
  const supabase = createClient()
  
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setMessage(null)

    const { error, data } = await supabase.auth.signUp({
      email,
      password,
    })

    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      setMessage("Signup successful! Please log in.")
      router.push("/login")
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-black/95 p-4 star-pattern">
      <div className="max-w-md w-full space-y-8">
        <Card className="bg-zinc-950/80 border-cyan-900/50 shadow-[0_0_15px_rgba(34,211,238,0.05)] backdrop-blur-xl overflow-hidden rounded-xl">
          <CardHeader className="space-y-2 border-b border-white/5 bg-white/[0.02]">
            <CardTitle className="text-2xl font-bold tracking-tight text-white">Admin Signup</CardTitle>
            <CardDescription className="text-zinc-400">
              Create an account to manage your tenant and access the admin chat.
            </CardDescription>
          </CardHeader>
          <form onSubmit={handleSignup}>
            <CardContent className="space-y-4 pt-6">
              {error && (
                <div className="p-3 text-sm rounded-md bg-red-950/50 border border-red-900/50 text-red-400">
                  {error}
                </div>
              )}
              {message && (
                <div className="p-3 text-sm rounded-md bg-green-950/50 border border-green-900/50 text-green-400">
                  {message}
                </div>
              )}
              <div className="space-y-2">
                <Button 
                  type="button" 
                  variant="outline" 
                  onClick={() => supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: `${location.origin}/api/auth/callback` } })}
                  className="w-full bg-white/5 border-white/10 text-white hover:bg-white/10 hover:text-white"
                >
                  <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
                    <path
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                      fill="#4285F4"
                    />
                    <path
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                      fill="#34A853"
                    />
                    <path
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                      fill="#FBBC05"
                    />
                    <path
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                      fill="#EA4335"
                    />
                  </svg>
                  Sign up with Google
               </Button>
              </div>
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-white/10" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-zinc-950/80 px-2 text-zinc-500">Or continue with</span>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email" className="text-zinc-300">Email</Label>
                <Input 
                  id="email" 
                  type="email" 
                  placeholder="admin@example.com" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  className="bg-black/50 border-white/10 text-white placeholder:text-white/20 focus-visible:ring-1 focus-visible:ring-cyan-500/50" 
                  required 
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-zinc-300">Password</Label>
                </div>
                <Input 
                  id="password" 
                  type="password" 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  className="bg-black/50 border-white/10 text-white placeholder:text-white/20 focus-visible:ring-1 focus-visible:ring-cyan-500/50" 
                  required 
                />
              </div>
            </CardContent>
            <CardFooter className="flex flex-col space-y-4 pt-2 pb-6 border-t border-white/5 bg-white/[0.01]">
              <Button 
                type="submit" 
                className="w-full bg-cyan-600/10 text-cyan-400 hover:bg-cyan-600/20 border border-cyan-500/20"
                disabled={loading}
              >
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {loading ? "Signing up..." : "Sign up"}
              </Button>
              <div className="text-sm text-center text-zinc-400">
                Already have an account?{' '}
                <a href="/login" className="text-cyan-400 hover:underline hover:text-cyan-300">
                  Log in
                </a>
              </div>
            </CardFooter>
          </form>
        </Card>
      </div>
    </div>
  )
}
