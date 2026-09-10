import http from './http'

// 认证
export const login = (data) => http.post('/auth/login', data)
export const me = () => http.get('/auth/me')

// 课程 / 知识图谱
export const listCourses = () => http.get('/courses')
export const courseKnowledge = (cid) => http.get(`/courses/${cid}/knowledge`)
export const listDimensions = () => http.get('/dimensions')
export const abilityDomains = () => http.get('/ability-domains')
// 课程能力维度开关(M11)
export const courseDimensions = (cid) => http.get(`/courses/${cid}/dimensions`)
export const setCourseDimensions = (cid, disabled) => http.put(`/courses/${cid}/dimensions`, { disabled })

// 题库
export const listItems = (params) => http.get('/items', { params })
export const itemTypes = () => http.get('/items/types')
export const getItem = (id) => http.get(`/items/${id}`)
export const createItem = (data) => http.post('/items', data)
export const updateItem = (id, data) => http.put(`/items/${id}`, data)
export const publishItem = (id, comment) => http.post(`/items/${id}/publish`, null, { params: { comment: comment || undefined } })
export const toggleItem = (id, enabled) => http.post(`/items/${id}/toggle`, null, { params: { enabled } })
export const deleteItem = (id) => http.delete(`/items/${id}`)
// 版本快照 / 比较 / 发布复核状态(M10)
export const itemVersions = (id) => http.get(`/items/${id}/versions`)
export const itemVersion = (id, v) => http.get(`/items/${id}/versions/${v}`)
export const compareVersions = (id, v1, v2) => http.get(`/items/${id}/versions/compare`, { params: { v1, v2 } })
export const publishStatus = (id) => http.get(`/items/${id}/publish-status`)

// 量规模板(M10)
export const listRubricTemplates = (params) => http.get('/rubric-templates', { params })
export const createRubricTemplate = (data) => http.post('/rubric-templates', data)
export const updateRubricTemplate = (id, data) => http.put(`/rubric-templates/${id}`, data)
export const deleteRubricTemplate = (id) => http.delete(`/rubric-templates/${id}`)

// 自主练习(学生)
export const practiceItems = (params) => http.get('/practice/items', { params })

// 答卷 / 成绩
export const submitAnswer = (data) => http.post('/answers', data)
// 口语录音上传契约(M4): multipart form = { item_id, content(转写), asr_note?, audio }
export const submitAnswerAudio = (formData) => http.post('/answers/audio', formData)
// 图片作答(识图转文字): multipart form = { item_id, image }
export const submitAnswerImage = (formData) => http.post('/answers/image', formData)
// 视频作答(基础版): multipart form = { item_id, video }
export const submitAnswerVideo = (formData) => http.post('/answers/video', formData)
export const studentOverview = (token) => http.get(`/scores/overview/${token}`)
export const listScores = (params) => http.get('/scores', { params })
export const getScore = (id) => http.get(`/scores/${id}`)

// 复核
export const reviewQueue = (params) => http.get('/reviews/queue', { params })
export const reviewRecent = (params) => http.get('/reviews/recent', { params })
export const doReview = (id, data) => http.post(`/reviews/${id}`, data)

// 引擎信息(技术铭牌: 任意登录角色可读)
export const engineMeta = () => http.get('/meta')

// 诊断 / 指标 / 审计
export const getDiagnosis = (token, courseId) =>
  http.get(`/diagnosis/${token}`, { params: courseId ? { course_id: courseId } : {} })
export const myDiagnosis = () => http.get('/diagnosis/mine/current')
export const qualityMetrics = () => http.get('/metrics/quality')
export const auditList = (params) => http.get('/audit', { params })

export default {
  login, me, listCourses, courseKnowledge, listDimensions, abilityDomains,
  courseDimensions, setCourseDimensions,
  practiceItems,
  listItems, itemTypes, getItem, createItem, updateItem, publishItem, toggleItem, deleteItem,
  itemVersions, itemVersion, compareVersions, publishStatus,
  listRubricTemplates, createRubricTemplate, updateRubricTemplate, deleteRubricTemplate,
  submitAnswer, submitAnswerAudio, submitAnswerImage, submitAnswerVideo, studentOverview, listScores, getScore,
  reviewQueue, reviewRecent, doReview,
  engineMeta,
  getDiagnosis, myDiagnosis, qualityMetrics, auditList,
}
