pipeline {
    agent any

    // 1. 参数化构建：让你在 Jenkins 界面点按钮时可以选择环境和用例类型
    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        // 2. 核心配置：Python 绝对路径 (根据你的实际路径修改)
        // 注意：Groovy 字符串中 Windows 路径建议用 / 或者 \\
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'

        // 3. Allure 报告路径定义
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT = 'reports/allure-report'
    }

    stages {
        stage('1. 拉取代码') {
            steps {
                echo "正在从 Git 拉取代码..."
                // 请替换为你真实的 Git 仓库地址
                git branch: 'main', url: 'https://github.com/yiming2333/api_test.git'
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                // 使用绝对路径调用 pip，-q 减少日志输出
                bat "${PYTHON_PATH} -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple"
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                // Windows 下使用 bat
                // ^ 是 Windows 批处理的换行符
                // || exit /b 0 确保即使测试失败，流水线也能继续走到生成报告阶段
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
                // 调用 Jenkins 全局工具配置的 Allure
                allure includeProperties: false,
                       jdk: '',
                       properties: [],
                       reportBuildPolicy: 'ALWAYS',
                       results: [[path: "${ALLURE_RESULTS}"]]
            }
        }
    }

    post {
        always {
            echo "流水线执行结束，清理工作..."
            // 归档日志文件，方便排查问题
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
        }
        success {
            echo "✅ 恭喜！所有测试用例通过！"
        }
        failure {
            echo "❌ 警告：存在失败的测试用例，请查看 Allure 报告详情。"
        }
    }
}