import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Spinner } from './components/ui'
import TeacherShell from './components/TeacherShell'
import Auth from './pages/Auth'
import Join from './pages/Join'
import Landing from './pages/Landing'
import NotFound from './pages/NotFound'
import Play from './pages/Play'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const CreateQuiz = lazy(() => import('./pages/CreateQuiz'))
const EditQuiz = lazy(() => import('./pages/EditQuiz'))
const HostGame = lazy(() => import('./pages/HostGame'))
const Reports = lazy(() => import('./pages/Reports'))
const ReportView = lazy(() => import('./pages/ReportView'))
const ReviewMine = lazy(() => import('./pages/ReviewMine'))

const Loading = (
  <div className="grid min-h-screen place-items-center">
    <Spinner />
  </div>
)

export default function App() {
  return (
    <Suspense fallback={Loading}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Auth mode="login" />} />
        <Route path="/signup" element={<Auth mode="signup" />} />
        <Route path="/join" element={<Join />} />
        <Route path="/play" element={<Play />} />
        <Route path="/play/review" element={<ReviewMine />} />

        <Route path="/teacher" element={<TeacherShell />}>
          <Route index element={<Dashboard />} />
          <Route path="new" element={<CreateQuiz />} />
          <Route path="quiz/:quizId" element={<EditQuiz />} />
          <Route path="reports" element={<Reports />} />
          <Route path="reports/:sessionId" element={<ReportView />} />
        </Route>
        <Route path="/teacher/host/:sessionId" element={<TeacherShell bare />}>
          <Route index element={<HostGame />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
