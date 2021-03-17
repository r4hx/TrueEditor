import asyncio
import base64
import logging
import os
from collections import deque
from io import BytesIO

import aiohttp
import translators as ts
from aiogram import Bot, Dispatcher, executor, types
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class Translate:
    def __init__(self, from_language="en", to_language="ru") -> None:
        self.from_language = from_language
        self.to_language = to_language

    def auto(self, text) -> str:
        self.text = text
        return str(
            ts.google(
                self.text,
                from_language=self.from_language,
                to_language=self.to_language,
            )
        )


class WordPress:
    def __init__(self, site_url, username, password) -> None:
        self.site_url = site_url
        self.api_url = f"{self.site_url}/wp-json/wp/v2"
        self.username = username
        self.password = password
        self.credentials = f"{self.username}:{self.password}"
        self.token = base64.b64encode(self.credentials.encode())
        self.headers = {
            "Authorization": "Basic " + self.token.decode("utf-8"),
        }

    async def upload_image(self, image_url, title, description):
        self.image_url = image_url
        self.title = title
        self.alt_text = title
        self.caption = title
        self.description = description
        self.filename = BytesIO()
        self.filename = os.path.basename(image_url)
        async with aiohttp.ClientSession() as self.session:
            async with self.session.get(f"{self.image_url}") as self.response:
                assert self.response.status == 200
                with open(self.filename, "wb") as self.f:
                    self.f.write(await self.response.read())
                self.data = {
                    "file": open(self.filename, "rb"),
                    "title": self.title,
                    "alt_text": self.alt_text,
                    "caption": self.caption,
                    "description": self.description,
                }
                async with self.session.post(
                    f"{self.api_url}/media",
                    headers=self.headers,
                    data=self.data,
                ) as self.response:
                    assert self.response.status == 201
                    os.remove(self.filename)
                    return await self.response.json()

    async def create_post(self, title, content, featured_media, status="draft"):
        self.title = title
        self.status = status
        self.content = content
        self.featured_media = featured_media
        self.data = {
            "title": self.title,
            "status": self.status,
            "content": self.content,
            "featured_media": self.featured_media,
        }
        async with aiohttp.ClientSession() as self.session:
            async with self.session.post(
                f"{self.api_url}/posts", headers=self.headers, json=self.data
            ) as self.response:
                assert self.response.status == 201
                return await self.response.json()


class MacRumors:
    def __init__(self, sitemap) -> None:
        self.sitemap = sitemap
        self.cache_file = "macrumors.txt"
        self.current_post_url = deque()
        self.current_post_title = deque()
        self.current_post_description = deque()
        self.current_post_cover = deque()
        self.current_post_text = deque()

    async def new_post_get_from_sitemap(self):
        async with aiohttp.ClientSession() as self.session:
            async with self.session.get(f"{self.sitemap}") as self.response:
                assert self.response.status == 200
                self.soup = BeautifulSoup(
                    await self.response.text(), features="html.parser"
                )
        self.source = [self.i.text for self.i in self.soup.find_all("loc")]
        self.cached = [
            self.i.strip() for self.i in open(self.cache_file, "r").readlines()
        ]
        self.post_url = []
        [
            self.post_url.append(self.i)
            for self.i in self.source
            if self.i not in self.cached
        ]
        return self.post_url[0]

    async def get_context_from_url(self, url):
        self.url = url
        async with aiohttp.ClientSession() as self.session:
            async with self.session.get(f"{self.url}") as self.response:
                assert self.response.status == 200
                return await self.response.text()

    def get_title(self, context):
        self.context = context
        self.soup = BeautifulSoup(self.context, features="html.parser")
        self.title = self.soup.find("meta", property="og:title")
        self.current_post_title.append(self.title.get("content", None))
        return self.title.get("content", None)

    def get_description(self, context):
        self.context = context
        self.soup = BeautifulSoup(self.context, features="html.parser")
        self.description = self.soup.find("meta", property="og:description")
        self.current_post_description.append(self.description.get("content", None))
        return self.description.get("content", None)

    def get_cover(self, context):
        self.context = context
        self.soup = BeautifulSoup(self.context, features="html.parser")
        self.image = self.soup.find("meta", property="og:image")
        self.current_post_cover.append(self.image.get("content", None))
        return self.image.get("content", None)

    def get_text(self, context):
        self.context = context
        self.soup = BeautifulSoup(self.context, features="html.parser")
        self.text = self.soup.find("article")
        self.current_post_text.append(self.text.contents[-2].text)
        return self.text.contents[-2].text


class Telegram:
    def __init__(self, token):
        self.token = token
        self.bot = Bot(token=self.token)
        self.dp = Dispatcher(self.bot)
        self.loop = asyncio.get_event_loop()

    def __new__(cls, token):
        """make singltone objects"""
        if not hasattr(cls, "instance"):
            cls.instance = super(Telegram, cls).__new__(cls)
        return cls.instance

    def keyboard_full_menu(self):
        self.keyboard_markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            row_width=4,
            one_time_keyboard=False,
            selective=True,
        )
        self.keyboard_markup.row("Добавить", "Получить")
        return self.keyboard_markup

    async def add(self, message: types.Message):
        await self.bot.send_message(
            message.chat.id,
            text="Ожидайте, идет обработка запроса.",
        )
        self.post_url = m.current_post_url.pop()
        self.title = t.auto(m.current_post_title.pop())
        self.description = t.auto(m.current_post_description.pop())
        self.cover = m.current_post_cover.pop()
        self.text = t.auto(m.current_post_text.pop())
        self.cover_upload = await self.loop.create_task(
            w.upload_image(
                image_url=self.cover, title=self.title, description=self.description
            )
        )
        self.post = await self.loop.create_task(
            w.create_post(
                title=self.title,
                content=self.text,
                featured_media=self.cover_upload["id"],
            )
        )
        if isinstance(self.post.get("id", None), int):
            with open(m.cache_file, "+a") as f:
                f.write(f"{self.post_url}\n")

        await self.bot.send_message(
            message.chat.id,
            text="Статья добавлена.",
            reply_markup=self.keyboard_full_menu(),
        )
        await self.bot.send_message(
            message.chat.id,
            text=f"{w.site_url}/wp-admin/post.php?post={self.post['id']}&action=edit",
            reply_markup=self.keyboard_full_menu(),
        )

    async def refresh(self, message: types.Message):
        try:
            self.post_url = m.current_post_url.pop()
            with open(m.cache_file, "+a") as f:
                f.write(f"{self.post_url}\n")
        except IndexError:
            pass
        self.url = await self.loop.create_task(m.new_post_get_from_sitemap())
        self.context = await m.get_context_from_url(self.url)
        m.current_post_url.append(self.url)
        self.cover = m.get_cover(self.context)
        m.current_post_cover.append(self.cover)
        self.title = m.get_title(self.context)
        m.current_post_title.append(self.title)
        self.description = m.get_description(self.context)
        m.current_post_description.append(self.description)
        self.text = m.get_text(self.context)
        m.current_post_text.append(self.text)
        await self.bot.send_message(
            message.chat.id,
            text=f"{self.url}",
            reply_markup=self.keyboard_full_menu(),
        )


if __name__ == "__main__":
    t = Translate()
    w = WordPress(
        site_url=os.getenv("WORDPRESS_SITE_URL"),
        username=os.getenv("WORDPRESS_LOGIN"),
        password=os.getenv("WORDPRESS_PASSWORD"),
    )
    m = MacRumors(sitemap=os.getenv("MACRUMOR_SITEMAP"))
    tg = Telegram(token=os.getenv("TELEGRAM_BOT_TOKEN"))
    tg.dp.register_message_handler(tg.add, text=["Добавить"])
    tg.dp.register_message_handler(tg.refresh, text=["Получить"])
    executor.start_polling(tg.dp, skip_updates=True)
