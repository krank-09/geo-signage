export function TokenBox({ deviceId, token }: { deviceId: string; token: string }) {
  return (
    <div className="rounded-lg bg-amber-50 p-3 text-sm ring-1 ring-amber-200">
      <p className="font-medium text-amber-900">Registration token (shown once)</p>
      <code className="my-2 block rounded bg-white px-3 py-2 text-lg font-bold tracking-wider">{token}</code>
      <p className="text-xs text-amber-800">Start the device with:</p>
      <code className="mt-1 block break-all rounded bg-ink-900 p-2 text-xs text-ink-100">
        python device/agent.py --server http://localhost:8000 --device-id {deviceId} --token {token}
      </code>
      <p className="mt-3 text-xs text-amber-800">Or use a phone or tablet as the display: open this link in its browser (needs https, so use the tunnel address, or localhost):</p>
      <code className="mt-1 block break-all rounded bg-ink-900 p-2 text-xs text-ink-100">{`${location.origin}/display/#id=${deviceId}&token=${token}`}</code>
    </div>
  )
}
