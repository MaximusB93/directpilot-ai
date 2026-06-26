import { postJson } from './api.js';

export function requestEmailCode(email) {
  return postJson('/auth/email/request-code', { email }, 'Не удалось отправить код');
}

export function verifyEmailCode(email, code) {
  return postJson('/auth/email/verify-code', { email, code }, 'Не удалось подтвердить код');
}
