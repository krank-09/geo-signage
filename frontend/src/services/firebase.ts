/** Firebase Authentication, loaded on demand so it costs nothing when Firebase is not configured on the server. */
import type { FirebaseApp } from 'firebase/app'
import type { Auth } from 'firebase/auth'
import type { AuthConfig } from '../types'

type Config = NonNullable<AuthConfig['firebase']>
let cached: { app: FirebaseApp; auth: Auth } | null = null

async function init(cfg: Config) {
  if (cached) return cached
  const [{ initializeApp }, authMod] = await Promise.all([import('firebase/app'), import('firebase/auth')])
  const app = initializeApp({ apiKey: cfg.apiKey, authDomain: cfg.authDomain, projectId: cfg.projectId, appId: cfg.appId })
  const auth = authMod.getAuth(app)
  if (cfg.emulatorHost) authMod.connectAuthEmulator(auth, `http://${cfg.emulatorHost}`, { disableWarnings: true })
  cached = { app, auth }
  return cached
}

export async function googleIdToken(cfg: Config): Promise<string> {
  const { auth } = await init(cfg)
  const { GoogleAuthProvider, signInWithPopup } = await import('firebase/auth')
  return (await signInWithPopup(auth, new GoogleAuthProvider())).user.getIdToken()
}

export async function emailIdToken(cfg: Config, email: string, password: string): Promise<string> {
  const { auth } = await init(cfg)
  const { signInWithEmailAndPassword } = await import('firebase/auth')
  return (await signInWithEmailAndPassword(auth, email, password)).user.getIdToken(true)
}

/** Creates the account and sends the verification email; the person signs in after clicking the link. */
export async function registerEmail(cfg: Config, email: string, password: string): Promise<void> {
  const { auth } = await init(cfg)
  const { createUserWithEmailAndPassword, sendEmailVerification, signOut } = await import('firebase/auth')
  const cred = await createUserWithEmailAndPassword(auth, email, password)
  await sendEmailVerification(cred.user)
  await signOut(auth)
}

export async function resendVerification(cfg: Config, email: string, password: string): Promise<void> {
  const { auth } = await init(cfg)
  const { signInWithEmailAndPassword, sendEmailVerification, signOut } = await import('firebase/auth')
  const cred = await signInWithEmailAndPassword(auth, email, password)
  await sendEmailVerification(cred.user)
  await signOut(auth)
}

const MESSAGES: Record<string, string> = {
  'auth/invalid-credential': 'Wrong email or password.',
  'auth/wrong-password': 'Wrong email or password.',
  'auth/user-not-found': 'No account with that email. Use “Create account”.',
  'auth/email-already-in-use': 'That email already has an account. Try signing in.',
  'auth/weak-password': 'Choose a password with at least 6 characters.',
  'auth/invalid-email': 'That email address does not look right.',
  'auth/too-many-requests': 'Too many attempts. Wait a minute and try again.',
  'auth/popup-closed-by-user': 'The Google window was closed before signing in.',
  'auth/popup-blocked': 'Your browser blocked the Google window. Allow pop-ups for this site and try again.',
  'auth/unauthorized-domain': 'This site’s address is not on the Firebase project’s authorised domains list (Firebase console, Authentication, Settings).',
  'auth/operation-not-allowed': 'That sign-in method is not enabled in the Firebase console yet.',
  'auth/network-request-failed': 'Could not reach Firebase. Check your internet connection.',
}
export const firebaseError = (e: unknown): string => MESSAGES[(e as { code?: string })?.code ?? ''] ?? (e as Error)?.message ?? 'Sign-in failed.'
