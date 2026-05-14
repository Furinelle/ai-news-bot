import unittest

from ai_news_bot.schedule import (
    add_subscription,
    normalize_schedule_time,
    remove_subscription,
    resolve_schedule_settings,
)


class ScheduleTests(unittest.TestCase):
    def test_normalize_schedule_time_accepts_hh_mm_and_rejects_invalid_values(self):
        self.assertEqual(normalize_schedule_time("8:05"), "08:05")
        self.assertEqual(normalize_schedule_time("23:59"), "23:59")

        with self.assertRaises(ValueError):
            normalize_schedule_time("24:00")
        with self.assertRaises(ValueError):
            normalize_schedule_time("8点")

    def test_chat_subscription_overrides_config_targets_after_first_use(self):
        state = add_subscription(
            saved_state=None,
            config_targets="wechat:group:old",
            target="wechat:private:me",
            schedule_time="8:30",
        )

        resolved = resolve_schedule_settings(
            config_time="09:00",
            config_targets="wechat:group:old",
            saved_state=state,
        )

        self.assertEqual(resolved.schedule_time, "08:30")
        self.assertEqual(resolved.targets, ["wechat:group:old", "wechat:private:me"])

    def test_unsubscribe_persists_empty_target_list_without_falling_back_to_config(self):
        state = remove_subscription(
            saved_state=None,
            config_targets="wechat:private:me",
            target="wechat:private:me",
        )

        resolved = resolve_schedule_settings(
            config_time="09:00",
            config_targets="wechat:private:me",
            saved_state=state,
        )

        self.assertEqual(resolved.schedule_time, "09:00")
        self.assertEqual(resolved.targets, [])


if __name__ == "__main__":
    unittest.main()
