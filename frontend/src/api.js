// One place for talking to the Flask API, so every page handles responses and errors the same way

export async function apiRequest(path, { method = 'GET', body } = {}) {
  const options = { method, headers: {} }

  // Requests with data send it as JSON, which is what the API expects (API.md)
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(path, options)
  } catch {
    // fetch itself only fails when the server can't be reached at all (offline, server down)
    throw new Error("Couldn't reach the server. Check your connection and try again.")
  }

  // 204 "No Content" has no body to read
  if (response.status === 204) {
    return null
  }

  // Every API response is JSON, including errors, which look like {"error": "..."}
  let data = null
  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    const error = new Error(data?.error || `Something went wrong (error ${response.status}).`)
    error.status = response.status
    throw error
  }

  return data
}
