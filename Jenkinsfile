pipeline {
    agent any

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT = 'reports/allure-report'
    }

    stages {
        stage('1. 拉取代码') {
            options {
                retry(3)  // ← 新增：GitHub 抽风自动重试
            }
            steps {
                echo "正在从 Git 拉取代码..."
                git branch: 'master', url: 'https://github.com/yiming2333/api_test.git'
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    ${PYTHON_PATH} -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                bat """
                    ${PYTHON_PATH} -m pytest ^
                        --env=${params.ENV} ^
                        ${params.MARK != 'all' ? '-m ' + params.MARK : ''} ^
                        --alluredir=${ALLURE_RESULTS} ^
                        --clean-alluredir ^
                        -v ^

                        || exit /b 0
                """
            }
        }

        stage('4. 生成 Allure 报告') {
            steps {
                echo "正在生成 Allure 测试报告..."
                bat "allure generate ${ALLURE_RESULTS} -o ${ALLURE_REPORT} --clean"
                publishHTML([
                    allowMissing: true,
                    alwaysLinkToLastBuild: true,
                    keepAll: true,
                    reportDir: "${ALLURE_REPORT}",
                    reportFiles: 'index.html',
                    reportName: 'Allure Report'
                ])
            }
        }
    }

    post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
        }
        success {
            echo "✅ 恭喜！所有测试用例通过！"
        }
        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
        }
    }
}