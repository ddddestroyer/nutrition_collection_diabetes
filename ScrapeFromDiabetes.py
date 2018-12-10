import os
import time
import re
import requests
from logging import getLogger, INFO, DEBUG, FileHandler, Formatter, StreamHandler
import numpy as np
import pandas as pd
import sys
import traceback
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.common.exceptions import TimeoutException

BASE_URL = "https://www.diabetesfoodhub.org/all-recipes.html"
PROJECT_ROOT = "/Users/d/nutrition_collection_diabetes"

class DiabetesScraper:

    def __init__(self, logger):
        self.logger = logger

    # カテゴリのURLとテキストデータの抽出
    def extract_category(self, category_list_url):

        time.sleep(1)
        category_list_page_html = requests.get(category_list_url).content
        category_list_page_soup = BeautifulSoup(category_list_page_html, "lxml")
        category_div = category_list_page_soup.find("div", {"data-type": "cuisines"})
        category_label = category_div.find_all("label")
        return [[i + 1, category.span.text] for i, category in enumerate(category_label)]

    # カテゴリの取得
    def scrape_category(self):

        category_list = self.extract_category(f"{BASE_URL}")
        category_columns = ["id", "name"]
        category_master_df = pd.DataFrame(category_list, columns=category_columns)
        category_master_df.to_csv(f"{PROJECT_ROOT}/data/category_master.csv", index=False, encoding='utf-8')
        self.logger(category_master_df)

        return category_master_df

    # 料理情報の取得
    def scrape_cooking_info(self, recipe_page_soup, cooking_id):

        cooking_info = {}
        cooking_info['cooking_id'] = cooking_id
        # 料理名
        cooking_info['cooking_name'] = recipe_page_soup.find('span', {'itemprop': 'name'}).text
        # Description
        try:
            if recipe_page_soup.find('div', class_='recipe__description').p:
                cooking_info['description'] = re.sub('\n', '', re.sub('\t', '', recipe_page_soup.find('div',
                                                                                                      class_='recipe__description').p.contents[
                    0]))
            elif recipe_page_soup.find('div', class_='recipe__description').contents[0]:
                cooking_info['description'] = re.sub('\n', '', re.sub('\t', '', recipe_page_soup.find('div',
                                                                                                      class_='recipe__description').contents[
                    0]))
            else:
                cooking_info['description'] = ''
        except:
            cooking_info['description'] = ''
        # 何人前か
        cooking_info['for_how_many_people'] = recipe_page_soup.find('div', class_='nutrition__content').p.text
        try:
            serving_ul_tag = recipe_page_soup.find('ul', class_='nutrition__servings')
            cooking_info["serving_size"] = serving_ul_tag.find('div', {'itemprop': 'servingSize'}).b.text
        except AttributeError:
            cooking_info['serving_size'] = ''
        # self.testObject.test_scrape_cooking_info(cooking_info)

        return cooking_info

    # 材料の取得
    def scrape_ingredients(self, recipe_page_soup):

        ingredients_list = []
        ingredients_li_tags = recipe_page_soup.find_all('li', {'itemprop': 'recipeIngredient'})
        for ingredients_li_tag in ingredients_li_tags:
            ingredients = {}
            # 材料の名前・分量が載っていない場合スキップする
            if ingredients_li_tag.dl.dt.b == None or ingredients_li_tag.dl.find('dd', {
                'data-unit': 'us'}) == None or ingredients_li_tag.dl.find('dd', {'data-unit': 'metric'}) == None:
                continue

            ingredients["ingredients_name"] = ingredients_li_tag.dl.dt.b.text
            ingredients["quantity_us"] = ingredients_li_tag.dl.find('dd', {'data-unit': 'us'}).text
            ingredients["quantity_metric"] = ingredients_li_tag.dl.find('dd', {'data-unit': 'metric'}).text
            ingredients_list.append(ingredients)

        return ingredients_list

    # 栄養の取得
    def scrape_nutrition(self, recipe_page_soup):

        nutrition_list = []
        nutrition_ul_tag = recipe_page_soup.find('div', class_='nutrition__top').ul
        # カロリー
        calories = {}
        calories['nutrition_name'] = nutrition_ul_tag.find('span', class_='h3').b.text
        calories['quantity'] = nutrition_ul_tag.find('span', {'itemprop': 'calories'}).text
        nutrition_list.append(calories)
        # その他栄養
        nutrition_next_ul_tag = nutrition_ul_tag.find_next('ul')
        nutrition_li_tags = nutrition_next_ul_tag.find_all('li')

        for nutrition_li_tag in nutrition_li_tags:
            nutrition = {}
            if nutrition_li_tag.span.b:
                nutrition['nutrition_name'] = nutrition_li_tag.span.b.text
                if nutrition_li_tag.span.span:
                    nutrition['quantity'] = nutrition_li_tag.span.span.text
                else:
                    nutrition['quantity'] = nutrition_li_tag.span.contents[1]
            else:
                nutrition['nutrition_name'] = nutrition_li_tag.span.contents[0]
                nutrition['quantity'] = nutrition_li_tag.span.span.text

            nutrition_list.append(nutrition)

        return nutrition_list

    def save_recipe(self, recipe_page_url, cooking_id, category_dict={}):

        time.sleep(0.5)
        recipe_page_html = requests.get(recipe_page_url).content
        recipe_page_soup = BeautifulSoup(recipe_page_html, "lxml")

        # 料理情報
        cooking_info = self.scrape_cooking_info(recipe_page_soup, cooking_id)
        df_cooking_info = pd.DataFrame(columns=list(cooking_info.keys()) + list(category_dict.keys()))
        df_cooking_info.loc[0] = list(cooking_info.values()) + list(category_dict.values())
        df_cooking_info.to_csv(f"{PROJECT_ROOT}/data/cooking_info.csv", index=False, encoding="utf-8", header=False,
                               mode="a")

        # 材料
        ingredients_list = self.scrape_ingredients(recipe_page_soup)
        df_ingredients = pd.DataFrame(columns=["ingredients_name", "quantity_us", "quantity_metric"])
        for ingredient in ingredients_list:
            df_ingredients = df_ingredients.append(pd.Series(list(ingredient.values()), index=df_ingredients.columns),
                                                   ignore_index=True)
        df_ingredients["cooking_id"] = cooking_id
        df_ingredients.to_csv(f"{PROJECT_ROOT}/data/ingredients.csv", index=False, encoding="utf-8", header=False, mode="a")

        # 栄養
        nutrition_list = self.scrape_nutrition(recipe_page_soup)
        df_nutrition = pd.DataFrame(columns=["nutrition_name", "quantity"])
        for nutrition in nutrition_list:
            df_nutrition = df_nutrition.append(pd.Series(list(nutrition.values()), index=df_nutrition.columns),
                                               ignore_index=True)
        df_nutrition['cooking_id'] = cooking_id
        df_nutrition.to_csv(f"{PROJECT_ROOT}/data/nutrition.csv", index=False, encoding="utf-8", header=False, mode="a")

    def scrape(self):

        root_category_df = self.scrape_category()

        # webdriverを用いて各カテゴリごとにURLを取得する
        driver_path = os.path.expanduser('~/chromedriver')
        driver = webdriver.Chrome(driver_path)
        driver.get(f"{BASE_URL}")

        cooking_id_num = 0

        for num, category_row in root_category_df.iterrows():

            if num == 0:
                my_like = driver.find_element_by_link_text('My Likes')
                my_like.click()

                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.LINK_TEXT, 'Cuisines')))

                cuisines_elm = driver.find_element_by_link_text('Cuisines')
                cuisines_elm.click()

            time.sleep(3)
            label = driver.find_element_by_xpath(
                f'//*[@id="profile_form"]/div[3]/div/div[{category_row["id"]}]/div/label')
            label.click()

            if not num == 0:
                label_before = driver.find_element_by_xpath(
                    f'//*[@id="profile_form"]/div[3]/div/div[{category_row["id"]-1}]/div/label')
                label_before.click()

            time.sleep(3)
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CLASS_NAME, 'recipes__item')))

            # Load moreをクリックしてコンテンツを取得する
            while True:
                try:
                    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.LINK_TEXT, 'Load more')))
                    load_elm = driver.find_element_by_link_text('Load more')
                    load_elm.click()
                except TimeoutException:
                    print('next')
                    elm = driver.find_element_by_tag_name('body')
                    elm.send_keys(Keys.HOME)
                    time.sleep(3)
                    break
                except WebDriverException:
                    print('wait 3 seconds')
                    time.sleep(3)

            recipe_list_page_html = driver.page_source
            recipe_list_page_soup = BeautifulSoup(recipe_list_page_html, 'lxml')
            recipes_container = recipe_list_page_soup.find('div', class_='recipes')

            recipe_a_tags = recipes_container.find_all('a', href=re.compile('https://www.diabetesfoodhub.org/recipes/'))
            recipe_url_list = [link.get('href') for link in recipe_a_tags]

            for order_in_page, recipe_url in enumerate(recipe_url_list):

                order_in_page += 1
                cooking_id = order_in_page + cooking_id_num

                category_dict = {"root_id": category_row["id"]}
                self.save_recipe(f"{recipe_url}", cooking_id, category_dict)
            else:
                cooking_id_num += len(recipe_url_list)

        driver.close()


if __name__ == '__main__':

    logger = getLogger()
    logger.setLevel(DEBUG)
    formatter = Formatter(fmt='%(asctime)-15s: %(pathname)s:l-%(lineno)d:\n\t[%(levelname)s] %(message)s')

    stream_info_handler = StreamHandler(stream=sys.stdout)
    stream_info_handler.setLevel(DEBUG)
    stream_info_handler.setFormatter(fmt=formatter)
    logger.addHandler(stream_info_handler)

    diabetes_scraper = DiabetesScraper(logger)
    diabetes_scraper.scrape()


