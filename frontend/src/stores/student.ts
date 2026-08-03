import { defineStore } from 'pinia'
import { ref } from 'vue'
import { eduApi, type Student } from '../api/edu'

export const useStudentStore = defineStore('student', () => {
  const students = ref<Student[]>([])
  const current = ref<Student | null>(null)
  const sessionId = ref<number | null>(null)

  async function loadStudents() {
    students.value = await eduApi.listStudents()
    if (!current.value && students.value.length > 0) {
      current.value = students.value[0]
    }
  }

  function selectStudent(s: Student) {
    current.value = s
    sessionId.value = null
  }

  return { students, current, sessionId, loadStudents, selectStudent }
})