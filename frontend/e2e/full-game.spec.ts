import { expect, test, type Browser, type Page } from '@playwright/test'

const API = process.env.E2E_API ?? 'http://127.0.0.1:8000'

const opts = (letters: string[]) => letters.map((id) => ({ id, text: `Option ${id}` }))
const question = (n: number, correct: string) => ({
  type: 'mcq',
  text: `Question number ${n}: which option is right?`,
  options: opts(['A', 'B', 'C', 'D']),
  correct_option_ids: [correct],
  explanation: `Because ${correct} is right.`,
  subtopic: 'basics',
  time_limit_sec: 30,
})

async function joinAs(browser: Browser, pin: string, nick: string): Promise<Page> {
  const page = await (await browser.newContext({ viewport: { width: 390, height: 800 } })).newPage()
  await page.goto('/')
  await page.getByPlaceholder('000000').fill(pin)
  await page.getByRole('button', { name: 'Join game' }).click()
  await page.getByLabel('Your nickname').fill(nick)
  await page.getByRole('button', { name: 'Join', exact: true }).click()
  await page.waitForURL('**/play')
  return page
}

test('teacher hosts a game, three students play it, report is created', async ({
  browser,
  request,
}) => {
  // Setup through the API (no AI needed): teacher, a published 2-question quiz, a live game.
  const email = `e2e-${Date.now()}@example.com`
  const reg = await request.post(`${API}/api/auth/register`, {
    data: { email, password: 'correct-horse-battery', display_name: 'E2E Teacher' },
  })
  expect(reg.status()).toBe(201)
  const tokens = await reg.json()
  const auth = { Authorization: `Bearer ${tokens.access_token}` }
  const quiz = await (
    await request.post(`${API}/api/quizzes`, {
      headers: auth,
      data: {
        title: 'E2E quiz',
        topic: 'Testing',
        questions: [question(1, 'B'), question(2, 'C')],
      },
    })
  ).json()
  await request.patch(`${API}/api/quizzes/${quiz.id}`, {
    headers: auth,
    data: { status: 'published' },
  })
  const game = await (
    await request.post(`${API}/api/sessions`, { headers: auth, data: { quiz_id: quiz.id } })
  ).json()

  // Teacher opens the host screen already logged in.
  const teacher = await (
    await browser.newContext({ viewport: { width: 1280, height: 900 } })
  ).newPage()
  await teacher.addInitScript(
    ([a, r]) => {
      localStorage.setItem('lq.access', a)
      localStorage.setItem('lq.refresh', r)
    },
    [tokens.access_token, tokens.refresh_token],
  )
  await teacher.goto(`/teacher/host/${game.id}`)
  await expect(teacher.getByLabel(/^PIN \d/)).toBeVisible({ timeout: 15_000 })

  const ada = await joinAs(browser, game.pin, 'Ada')
  const bob = await joinAs(browser, game.pin, 'Bob')
  const cy = await joinAs(browser, game.pin, 'Cy')
  await expect(ada.getByText('You are in, Ada!')).toBeVisible()
  for (const nick of ['Ada', 'Bob', 'Cy']) await expect(teacher.getByText(nick)).toBeVisible()

  // Question 1: Ada right (B), Bob wrong (A), Cy right (B). Everyone answered, so it closes by itself.
  await teacher.getByRole('button', { name: 'Start game' }).click()
  await expect(ada.getByRole('timer')).toBeVisible({ timeout: 10_000 })
  await ada.locator('ul button').nth(1).click()
  await bob.locator('ul button').nth(0).click()
  await cy.locator('ul button').nth(1).click()
  await expect(ada.getByText('Correct!')).toBeVisible({ timeout: 10_000 })
  await expect(bob.getByText('Not this time')).toBeVisible({ timeout: 10_000 })
  await expect(ada.getByText('Because B is right.')).toBeVisible()

  // Leaderboard, then question 2: only Ada answers (C, right); the teacher closes it early.
  await teacher.getByRole('button', { name: 'Show leaderboard' }).click()
  await expect(ada.getByRole('heading', { name: 'Leaderboard' })).toBeVisible({ timeout: 10_000 })
  await teacher.getByRole('button', { name: 'Next question' }).click()
  await expect(bob.getByText(/Question 2 of 2/)).toBeVisible({ timeout: 10_000 })
  await ada.locator('ul button').nth(2).click()
  await teacher.getByRole('button', { name: 'End question now' }).click()
  await expect(bob.getByText('Too slow')).toBeVisible({ timeout: 10_000 })

  // End the game: every student gets a final screen with a rank, and the teacher a report link.
  await teacher.getByRole('button', { name: 'End game' }).click()
  await teacher.getByRole('button', { name: 'Yes, end the game' }).click()
  for (const p of [ada, bob, cy]) {
    await expect(p.getByRole('heading', { name: 'Game over' })).toBeVisible({ timeout: 10_000 })
    await expect(p.getByLabel('Your rank')).toBeVisible()
  }
  await expect(ada.getByLabel('Your rank')).toHaveText('#1')

  const link = teacher.getByRole('link', { name: 'View full report' })
  await expect(link).toBeVisible({ timeout: 10_000 })
  await link.click()
  await expect(teacher.getByText('E2E quiz').first()).toBeVisible()
  await expect(teacher.getByText('Players')).toBeVisible()
})
