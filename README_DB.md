## Применение миграций
yoyo apply \
  --database postgresql://vahta_user:ZT5s1paPknhfc1r0fl@localhost:5432/vahta_ai_db \
  migrations/


## Проверка статуса
yoyo list \
  --database postgresql://vahta_user:ZT5s1paPknhfc1r0fl@localhost:5432/vahta_ai_db \
  migrations/

## Откат миграции
yoyo rollback \
  --database postgresql://vahta_user:ZT5s1paPknhfc1r0fl@localhost:5432/vahta_ai_db \
  migrations/