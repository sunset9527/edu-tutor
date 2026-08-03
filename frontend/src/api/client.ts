import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

// 请求拦截：自动携带 token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('edututor_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：401 清除凭证并跳登录
client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (
      error?.response?.status === 401 &&
      !error.config?.url?.includes('/auth/')
    ) {
      localStorage.removeItem('edututor_token')
      localStorage.removeItem('edututor_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client