import { formatMoney } from "./money";

/** One Russian text per error code the API can return. A backend test fails if a code is missing here. */
type Params = Record<string, any> | undefined;

export const MESSAGES: Record<string, (p: Params) => string> = {
  // not an API code: produced by the client itself when the server cannot be reached
  network_error: () => "Нет связи с сервером. Ничего не потеряно: проверьте соединение и повторите, повтор не создаст дубль",
  // access
  not_authenticated: () => "Нужно войти в аккаунт",
  session_invalid: () => "Сессия недействительна или истекла, войдите снова",
  bad_credentials: () => "Неверный e-mail или пароль",
  too_many_attempts: () => "Слишком много неудачных попыток входа. Попробуйте через несколько минут",
  email_taken: () => "Этот e-mail уже зарегистрирован",
  // groups and members
  group_not_found: () => "Группа не найдена или у вас нет к ней доступа",
  not_found: () => "Не найдено",
  invite_invalid: () => "Ссылка-приглашение недействительна",
  group_closed: () => "Группа закрыта",
  group_not_closed: () => "Группа не закрыта",
  group_already_closed: () => "Группа уже закрыта",
  group_closed_expenses: () => "Группа закрыта: расходы нельзя добавлять и менять. Откройте её снова в настройках",
  group_closed_payments: () => "Группа закрыта: откройте её снова, чтобы записывать и подтверждать платежи",
  pending_before_close: () => "Сначала подтвердите или отклоните неподтверждённые платежи: итог не должен меняться после отправки",
  pending_payments: () => "Сначала подтвердите или отклоните неподтверждённые платежи",
  close_before_delete: () => "Сначала закройте группу (удалить её без закрытия можно, пока в ней нет расходов)",
  only_creator_remove: () => "Участников может убирать только создатель группы",
  only_creator_delete: () => "Группу может удалить только её создатель",
  use_leave: () => "Чтобы выйти самому, используйте кнопку «Выйти из группы»",
  last_member: () => "Последний участник не может выйти: удалите группу",
  not_member: () => "Этот человек не состоит в группе",
  balance_not_zero: () => "Сначала рассчитайтесь: баланс этого участника в группе не равен нулю",
  // expenses
  expense_not_found: () => "Расход не найден",
  expense_conflict: () => "Расход только что изменил кто-то другой. Обновите страницу и повторите правку",
  not_expense_owner: () => "Менять расход может только тот, кто его добавил, или плательщик",
  payer_not_member: () => "Плательщик должен быть участником группы",
  participant_not_member: () => "Все участники расхода должны быть в группе",
  split_invalid: () => "Не удалось разделить сумму",
  split_negative_total: () => "Сумма не может быть отрицательной",
  split_need_participants: () => "Выберите хотя бы одного участника",
  split_need_weights: () => "Укажите доли участников",
  split_need_amounts: () => "Укажите суммы участников",
  split_duplicate: () => "Участник указан дважды",
  split_bad_weights: () => "Доли должны быть целыми числами от 1",
  split_bad_amounts: () => "Суммы участников не могут быть отрицательными",
  split_exact_sum: () => "Суммы участников должны давать ровно сумму расхода",
  split_unbalanced: () => "Балансы не сходятся: сообщите разработчику",
  // receipts
  no_receipt: () => "У этого расхода нет чека",
  receipt_file_missing: () => "Файл чека не найден",
  receipt_bad_type: () => "Чек должен быть настоящим файлом PNG, JPEG, WebP или PDF",
  receipt_too_large: () => "Файл чека слишком большой (до 5 МБ)",
  // payments
  settlement_not_found: () => "Платёж не найден",
  settlement_resolved: (p) => `Этот платёж уже ${p?.status === "confirmed" ? "подтверждён" : p?.status === "rejected" ? "отклонён" : "обработан"}`,
  not_confirmer: () => "Подтвердить или отклонить платёж может только вторая сторона (не тот, кто его записал)",
  other_party_not_member: () => "Вторая сторона должна быть другим участником группы",
  owes_nothing: () => "Этот человек ничего не должен в группе",
  receiver_not_owed: () => "Получателю никто ничего не должен в этой группе",
  pending_cover_debt: () => "Уже отправленные платежи покрывают весь долг",
  amount_exceeds_limit: (p) =>
    `Сумма больше, чем можно закрыть между вами сейчас (максимум ${p?.max_minor != null ? formatMoney(p.max_minor, p.currency ?? "USD") : "—"})`,
  // retries
  idempotency_key_invalid: () => "Служебная ошибка: неверный ключ повтора запроса",
  idempotency_key_reused: () => "Служебная ошибка: этот ключ повтора уже использован для другого действия",
  // notifications
  notification_not_found: () => "Уведомление не найдено",
};

/** Texts for request-validation failures (the API answers 422 with a list of field errors). */
const FIELD_LABEL: Record<string, string> = {
  email: "E-mail", password: "Пароль", name: "Имя", amount_minor: "Сумма", currency: "Валюта", remind_after_days: "Срок напоминания",
  payer_id: "Плательщик", to_user: "Получатель", from_user: "Плательщик", participants: "Участники", weights: "Доли", amounts: "Суммы",
  title: "Название", comment: "Комментарий", category: "Категория", spent_on: "Дата",
};
const VALIDATION_HINTS: [RegExp, string][] = [
  [/unknown currency/i, "такой валюты нет в списке"],
  [/participants must not repeat/i, "участник указан дважды"],
  [/too many entries/i, "слишком много участников"],
  [/exactly one of to_user/i, "укажите, кто кому платит"],
  [/valid email|email address/i, "неверный адрес"],
];
const VALIDATION_TYPES: Record<string, string> = {
  missing: "обязательное поле",
  string_too_short: "слишком короткое значение",
  string_too_long: "слишком длинное значение",
  greater_than: "значение слишком маленькое",
  greater_than_equal: "значение слишком маленькое",
  less_than: "значение слишком большое",
  less_than_equal: "значение слишком большое",
  int_parsing: "нужно целое число",
  date_from_datetime_parsing: "неверная дата",
  date_parsing: "неверная дата",
};

export function validationText(list: any[]): string {
  return list
    .map((d) => {
      const field = FIELD_LABEL[String(d.loc?.[d.loc.length - 1])] ?? "";
      const msg = String(d.msg ?? "");
      const hint = VALIDATION_HINTS.find(([re]) => re.test(msg))?.[1] ?? VALIDATION_TYPES[d.type] ?? "некорректное значение";
      return field ? `${field}: ${hint}` : hint[0].toUpperCase() + hint.slice(1);
    })
    .join("; ");
}
